"""National ID must be reviewed before showing any registration fields."""
from types import MethodType
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.loanhub_registration_review import LoanHubRegistrationReview
from backend.app.loanhub_staff_verifier import LoanHubStaffVerifier
from backend.app.staff_authorization import VerifiedStaffIdentity
from backend.app.staff_login_routes import (
    COOKIE, CSRF_COOKIE, StaffLoginConfig, StagingStaffSessionStore,
)

COMPANY, USER, BRANCH, OTHER = (uuid4() for _ in range(4))
ORIGIN = "https://batlokoa-check.example"
UPSTREAM = "https://loanhub-check.example"
NATIONAL_ID = "SYNTHETIC-ID-DO-NOT-USE"


@pytest.fixture(autouse=True)
def reset():
    names = ("staff_login_config", "staff_registration_identity_review",
             "staff_registration_identity_review_enabled")
    for n in names:
        if hasattr(app.state, n):
            delattr(app.state, n)
    yield
    for n in names:
        if hasattr(app.state, n):
            delattr(app.state, n)


def setup(upstream_answer, *, enabled=True, verified=True):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=upstream_answer)

    upstream = httpx.Client(transport=httpx.MockTransport(handle))
    verifier = LoanHubStaffVerifier(
        origin=UPSTREAM, public_key="synthetic-test-key",
        batlokoa_company_id=COMPANY,
    )
    def verify(self, token):
        if not verified:
            from backend.app.loanhub_staff_verifier import StaffVerificationUnavailable
            raise StaffVerificationUnavailable()
        return VerifiedStaffIdentity(
            user_id=USER, company_id=COMPANY, role="LOAN_OFFICER",
            active=True, branch_ids=frozenset({BRANCH}),
        )
    verifier.verify = MethodType(verify, verifier)
    store = StagingStaffSessionStore()
    cookie, csrf = store.issue("synthetic-access", 300)
    app.state.staff_login_config = StaffLoginConfig(ORIGIN, UPSTREAM, verifier, store)
    app.state.staff_registration_identity_review = LoanHubRegistrationReview(
        origin=UPSTREAM, client=upstream)
    app.state.staff_registration_identity_review_enabled = enabled
    client = TestClient(app, base_url=ORIGIN)
    client.cookies.set(COOKIE, cookie)
    client.cookies.set(CSRF_COOKIE, csrf)
    return client, csrf, calls, upstream


def post(client, csrf, *, branch=BRANCH, origin=ORIGIN, national_id=NATIONAL_ID):
    return client.post(
        "/api/v1/staff/clients/national-id-check",
        headers={"Origin": origin, "x-csrf-token": csrf},
        json={"national_id": national_id, "branch_id": str(branch)},
    )


def answer(*, match=False, legacy=False):
    return {
        "decision": "manual_review_required" if match or legacy else "new_identity_candidate",
        "can_commit": False, "requires_human_review": True,
        "identity_match_found": match, "legacy_capture_found": legacy,
    }


@pytest.mark.parametrize("match,legacy,may_continue", [
    (False, False, True),
    (True, False, False),
    (False, True, False),
    (True, True, False),
])
def test_identity_review_blocks_existing_and_legacy_records(match, legacy, may_continue):
    client, csrf, calls, upstream = setup(answer(match=match, legacy=legacy))
    try:
        response = post(client, csrf)
        assert response.status_code == 200
        payload = response.json()
        assert payload["may_continue_preparation"] is may_continue
        assert payload["registration_authorized"] is False
        assert payload["human_review_required"] is True
        assert response.headers["cache-control"] == "no-store"
        assert NATIONAL_ID not in response.text
        assert "identity_match_found" not in response.text
        assert len(calls) == 1
        assert calls[0].method == "POST"
        assert calls[0].url.path == "/api/v1/company-clients/registration-review"
        assert NATIONAL_ID not in str(calls[0].url)
    finally:
        upstream.close()


def test_fail_closed_if_not_enabled():
    client, csrf, calls, upstream = setup(answer(), enabled=False)
    try:
        assert post(client, csrf).status_code == 503
        assert calls == []
    finally:
        upstream.close()


def test_origin_csrf_branch_and_session_denied():
    client, csrf, calls, upstream = setup(answer())
    try:
        assert post(client, csrf, origin="https://attacker.example").status_code == 403
        assert post(client, "wrong-token").status_code == 403
        assert post(client, csrf, branch=OTHER).status_code == 403
        assert calls == []
        client.cookies.delete(COOKIE)
        assert post(client, csrf).status_code == 401
    finally:
        upstream.close()


def test_unverified_upstream_response_is_not_no_match():
    client, csrf, calls, upstream = setup({
        "decision": "new_identity_candidate", "can_commit": True,
        "requires_human_review": False, "identity_match_found": False,
        "legacy_capture_found": False,
    })
    try:
        response = post(client, csrf)
        assert response.status_code == 503
        assert response.json() == {"code": "IDENTITY_CHECK_UNAVAILABLE"}
        assert NATIONAL_ID not in response.text
    finally:
        upstream.close()


def test_reject_extra_fields_and_national_id_in_query():
    client, csrf, calls, upstream = setup(answer())
    try:
        response = client.post(
            "/api/v1/staff/clients/national-id-check",
            headers={"Origin": ORIGIN, "x-csrf-token": csrf},
            json={"national_id": NATIONAL_ID, "branch_id": str(BRANCH),
                  "company_id": str(COMPANY)},
        )
        assert response.status_code == 422
        assert calls == []
    finally:
        upstream.close()
