"""HTTP registration preflight must never write, leak PII or grant submission."""
from datetime import date
from types import MethodType
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.loanhub_staff_verifier import (
    LoanHubStaffVerifier, StaffVerificationUnavailable,
)
from backend.app.staff_authorization import VerifiedStaffIdentity
from backend.app.staff_login_routes import (
    COOKIE, CSRF_COOKIE, StaffLoginConfig, StagingStaffSessionStore,
)

COMPANY, BRANCH, OTHER, USER = (uuid4() for _ in range(4))
ORIGIN = "https://batlokoa-stage.example"
UPSTREAM = "https://loanhub-stage.example"


@pytest.fixture(autouse=True)
def reset():
    for key in ("staff_login_config", "staff_registration_preflight_enabled"):
        if hasattr(app.state, key):
            delattr(app.state, key)
    yield
    for key in ("staff_login_config", "staff_registration_preflight_enabled"):
        if hasattr(app.state, key):
            delattr(app.state, key)


def draft(**changes):
    result = dict(first_name="Palesa", last_name="Test",
                  phone="59000000", date_of_birth="1990-01-01",
                  gender="female", district="Maseru",
                  employment_status="employed", branch_id=str(BRANCH),
                  national_id="SECRET-NATIONAL-ID",
                  passport_number=None, monthly_income="1250.00",
                  consent_to_share_profile=True,
                  consent_to_credit_checks=True)
    result.update(changes)
    return result


def setup(*, verified=True):
    verifier = LoanHubStaffVerifier(
        origin=UPSTREAM, public_key="test-only", batlokoa_company_id=COMPANY,
    )
    identity = VerifiedStaffIdentity(
        user_id=USER, company_id=COMPANY, role="LOAN_OFFICER",
        active=True, branch_ids=frozenset({BRANCH}),
    )
    def verify(self, token):
        if not verified:
            raise StaffVerificationUnavailable()
        assert token == "fake-verified-token"
        return identity
    verifier.verify = MethodType(verify, verifier)
    store = StagingStaffSessionStore()
    cookie, csrf = store.issue("fake-verified-token", 300)
    app.state.staff_login_config = StaffLoginConfig(
        ORIGIN, UPSTREAM, verifier, store,
    )
    app.state.staff_registration_preflight_enabled = True
    client = TestClient(app, base_url=ORIGIN)
    client.cookies.set(COOKIE, cookie)
    client.cookies.set(CSRF_COOKIE, csrf)
    return client, csrf


def post(client, csrf, payload=None, *, origin=ORIGIN):
    return client.post(
        "/api/v1/staff/clients/registration-preflight",
        json=draft() if payload is None else payload,
        headers={"origin": origin, "x-csrf-token": csrf},
    )


def test_disabled_even_if_body_supplies_identity_and_role():
    client = TestClient(app, base_url=ORIGIN)
    response = post(client, "pretend-csrf")
    assert response.status_code == 503
    assert response.json()["code"] == "REGISTRATION_PREFLIGHT_DISABLED"


def test_authenticated_valid_draft_never_grants_client_creation():
    client, csrf = setup()
    result = post(client, csrf)
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["validated"] is True
    assert data["identity_review_required"] is True
    assert data["can_submit"] is False
    assert data["branch_id"] == str(BRANCH)
    assert result.headers["cache-control"] == "no-store"
    assert "SECRET-NATIONAL-ID" not in result.text
    assert "59000000" not in result.text
    assert "1250" not in result.text
    assert "Palesa" not in result.text


def test_wrong_origin_csrf_and_cookie_are_denied():
    client, csrf = setup()
    assert post(client, csrf, origin="https://evil.example").status_code == 403
    assert post(client, "wrong-csrf-token").status_code == 403
    client.cookies.delete(COOKIE)
    assert post(client, csrf).status_code == 401


def test_revalidated_revoked_staff_session_is_denied():
    client, csrf = setup(verified=False)
    assert post(client, csrf).status_code == 401


def test_cross_branch_loan_officer_cannot_prepare_other_branch():
    client, csrf = setup()
    result = post(client, csrf, draft(branch_id=str(OTHER)))
    assert result.status_code == 403


@pytest.mark.parametrize("changes", [
    {"national_id": None, "passport_number": None},
    {"monthly_income": "NaN"},
    {"monthly_income": "5.001"},
    {"date_of_birth": "2099-01-01"},
    {"phone": "1"},
    {"first_name": ""},
    {"consent_to_credit_checks": "yes"},
    {"company_id": str(COMPANY)},
])
def test_invalid_or_unexpected_registration_data_fail_closed(changes):
    client, csrf = setup()
    response = post(client, csrf, draft(**changes))
    assert response.status_code == 422
    assert "SECRET-NATIONAL-ID" not in response.text


def test_request_does_not_use_legacy_client_create_route(monkeypatch):
    client, csrf = setup()
    # A valid preflight response is never a registration receipt.
    response = post(client, csrf)
    assert response.status_code == 200
    assert "account_id" not in response.json()
    assert "borrower_id" not in response.json()
    assert "application_id" not in response.json()
