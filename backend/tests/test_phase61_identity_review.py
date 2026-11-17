from uuid import uuid4
import httpx
import pytest
from backend.app.staff_authorization import VerifiedStaffIdentity, StaffAccessDenied
from backend.app.staff_identity_review import LoanHubIdentityReview, IdentityReviewUnavailable

COMPANY, BRANCH, OTHER, USER = (uuid4() for _ in range(4))
ID = "synthetic-1234"

def staff(**kw):
    p = dict(user_id=USER, company_id=COMPANY, role="LOAN_OFFICER",
             active=True, branch_ids=frozenset({BRANCH}))
    p.update(kw)
    return VerifiedStaffIdentity(**p)

def evidence(**kw):
    p = dict(national_id=ID, borrower_found=False, already_company_client=False,
             has_existing_loans=False, legacy_capture_count=0)
    p.update(kw)
    return p

def check(response, who=None, branch=BRANCH):
    calls = []
    def handler(req):
        calls.append(req)
        return response
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        r = LoanHubIdentityReview(origin="https://loanhub.example", client=client)
        result = r.review(staff=who or staff(), access_token="test-token",
                          branch_id=branch, national_id=ID)
    return result, calls

def test_clean_review_does_not_grant_write():
    value, calls = check(httpx.Response(200, json=evidence()))
    assert value.status == "no_existing_record_reported"
    assert value.can_register is False
    assert not hasattr(value, "national_id")
    assert calls[0].url.path == "/api/v1/company-clients/existing-loan-check"
    assert calls[0].headers["X-Company-ID"] == str(COMPANY)

@pytest.mark.parametrize("change,status", [
    ({"legacy_capture_count": 2}, "legacy_review_required"),
    ({"borrower_found": True}, "existing_borrower_review_required"),
    ({"borrower_found": True, "already_company_client": True}, "existing_company_client"),
])
def test_existing_identity_requires_review(change, status):
    value, _ = check(httpx.Response(200, json=evidence(**change)))
    assert value.status == status and not value.can_register

@pytest.mark.parametrize("change", [
    {"national_id": "other-id"}, {"legacy_capture_count": -1},
    {"legacy_capture_count": True}, {"borrower_found": "false"},
    {"already_company_client": True},
])
def test_invalid_evidence_rejected(change):
    with pytest.raises(IdentityReviewUnavailable):
        check(httpx.Response(200, json=evidence(**change)))

def test_upstream_denial_rejected():
    with pytest.raises(IdentityReviewUnavailable):
        check(httpx.Response(403, json={"detail": "Denied"}))

def test_wrong_branch_denied():
    with pytest.raises(StaffAccessDenied):
        check(httpx.Response(200, json=evidence()), branch=OTHER)

def test_borrower_denied():
    with pytest.raises(StaffAccessDenied):
        check(httpx.Response(200, json=evidence()), who=staff(role="BORROWER"))
