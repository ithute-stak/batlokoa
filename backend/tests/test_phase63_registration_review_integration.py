"""Read-only registration review adapter; no personal-data echo or write authority."""
from types import MethodType
from uuid import uuid4
import httpx
import pytest

from backend.app.loanhub_registration_review import (
    LoanHubRegistrationReview, RegistrationIdentityReviewUnavailable,
)
from backend.app.staff_authorization import (
    StaffAccessDenied, VerifiedStaffIdentity,
)
from backend.app.main import app
from fastapi.testclient import TestClient
from backend.app.staff_login_routes import (
    COOKIE, CSRF_COOKIE, StaffLoginConfig, StagingStaffSessionStore,
)
from backend.app.loanhub_staff_verifier import LoanHubStaffVerifier

COMPANY, USER, BRANCH, OTHER = (uuid4() for _ in range(4))
ORIGIN = "https://batlokoa-test.example"
UPSTREAM = "https://loanhub-test.example"


def employee():
    return VerifiedStaffIdentity(
        user_id=USER, company_id=COMPANY, role="LOAN_OFFICER",
        active=True, branch_ids=frozenset({BRANCH}),
    )


def adapter(response, calls):
    def mock(request):
        calls.append(request)
        return httpx.Response(200, json=response)
    client = httpx.Client(transport=httpx.MockTransport(mock))
    return LoanHubRegistrationReview(origin=UPSTREAM, client=client), client


def test_post_not_url_restricts_fields_and_never_allows_commit():
    calls = []
    review, client = adapter({
        "decision": "new_identity_candidate",
        "can_commit": False, "requires_human_review": True,
        "identity_match_found": False, "legacy_capture_found": False,
    }, calls)
    try:
        result = review.review(staff=employee(), access_token="verified-token",
                               branch_id=BRANCH, national_id="TEST-ID-12345")
        assert result.decision == "new_identity_candidate"
        assert result.requires_human_review
        assert result.can_commit is False
        assert len(calls) == 1
        assert calls[0].method == "POST"
        assert calls[0].url.path == "/api/v1/company-clients/registration-review"
        assert "TEST-ID" not in str(calls[0].url)
        assert calls[0].headers["authorization"] == "Bearer verified-token"
        assert calls[0].headers["x-company-id"] == str(COMPANY)
    finally:
        client.close()


@pytest.mark.parametrize("body", [
    {"decision": "new_identity_candidate", "can_commit": True,
     "requires_human_review": False, "identity_match_found": False,
     "legacy_capture_found": False},
    {"decision": "approved", "can_commit": False,
     "requires_human_review": True, "identity_match_found": False,
     "legacy_capture_found": False},
    {"decision": "manual_review_required", "can_commit": False,
     "requires_human_review": True, "identity_match_found": "false",
     "legacy_capture_found": False},
])
def test_untrusted_upstream_results_fail_closed(body):
    calls = []
    review, client = adapter(body, calls)
    try:
        with pytest.raises(RegistrationIdentityReviewUnavailable):
            review.review(staff=employee(), access_token="verified-token",
                          branch_id=BRANCH, national_id="TEST-ID-12345")
    finally:
        client.close()


def test_other_branch_never_contacts_loanhub():
    calls = []
    review, client = adapter({}, calls)
    try:
        with pytest.raises(StaffAccessDenied):
            review.review(staff=employee(), access_token="verified-token",
                          branch_id=OTHER, national_id="TEST-ID-12345")
        assert calls == []
    finally:
        client.close()


@pytest.fixture(autouse=True)
def reset_route_settings():
    names = ("staff_login_config", "staff_registration_preflight_enabled",
             "staff_registration_identity_review",
             "staff_registration_identity_review_enabled")
    for name in names:
        if hasattr(app.state, name):
            delattr(app.state, name)
    yield
    for name in names:
        if hasattr(app.state, name):
            delattr(app.state, name)


def test_opt_in_route_returns_no_write_review_and_avoids_pii():
    calls = []
    review, upstream = adapter({
        "decision": "manual_review_required", "can_commit": False,
        "requires_human_review": True, "identity_match_found": True,
        "legacy_capture_found": True,
    }, calls)
    try:
        verifier = LoanHubStaffVerifier(
            origin=UPSTREAM, public_key="test-only",
            batlokoa_company_id=COMPANY,
        )
        verifier.verify = MethodType(lambda self, token: employee(), verifier)
        store = StagingStaffSessionStore()
        cookie, csrf = store.issue("synthetic-token", 300)
        app.state.staff_login_config = StaffLoginConfig(
            ORIGIN, UPSTREAM, verifier, store,
        )
        app.state.staff_registration_preflight_enabled = True
        app.state.staff_registration_identity_review_enabled = True
        app.state.staff_registration_identity_review = review
        client = TestClient(app, base_url=ORIGIN)
        client.cookies.set(COOKIE, cookie)
        client.cookies.set(CSRF_COOKIE, csrf)
        res = client.post("/api/v1/staff/clients/registration-preflight",
            headers={"origin": ORIGIN, "x-csrf-token": csrf},
            json={
                "first_name": "Synthetic", "last_name": "Borrower",
                "phone": "59000000", "date_of_birth": "1990-01-01",
                "gender": "female", "district": "Maseru",
                "employment_status": "employed",
                "branch_id": str(BRANCH), "national_id": "TEST-ID-12345",
            })
        assert res.status_code == 200, res.text
        payload = res.json()
        assert payload["can_submit"] is False
        assert payload["identity_review"]["can_commit"] is False
        assert payload["identity_review"]["decision"] == "manual_review_required"
        assert payload["identity_review"]["requires_human_review"] is True
        assert "TEST-ID-12345" not in res.text
        assert "59000000" not in res.text
        assert len(calls) == 1
    finally:
        upstream.close()
