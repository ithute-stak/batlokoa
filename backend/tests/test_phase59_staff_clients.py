"""Network-free, fail-closed staff directory contract tests."""
from uuid import uuid4

import httpx
import pytest

from backend.app.loanhub_staff_clients import (
    LoanHubStaffClientDirectory, StaffDirectoryUnavailable,
)
from backend.app.staff_authorization import StaffAccessDenied, VerifiedStaffIdentity

COMPANY, BRANCH, OTHER_BRANCH, USER = (uuid4() for _ in range(4))


def staff(*, role="LOAN_OFFICER", company=COMPANY, branch=BRANCH):
    return VerifiedStaffIdentity(
        user_id=USER, company_id=company, role=role, active=True,
        branch_ids=frozenset({branch}) if branch else frozenset(),
        company_wide_scope=role in {"COMPANY_OWNER", "COMPANY_ADMIN"},
    )


def client_record(*, company=COMPANY, branch=BRANCH, name="Mpho Test"):
    return {
        "id": str(uuid4()), "company_id": str(company),
        "branch_id": str(branch) if branch else None,
        "full_name": name, "account_reference": "BFS-001",
        "status": "active",
        "national_id": "never-expose-this",
    }


def lookup(records, *, identity=None, target=None, status_code=200):
    calls = []
    def respond(req):
        calls.append(req)
        return httpx.Response(status_code, json=records)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        directory = LoanHubStaffClientDirectory(
            origin="https://loanhub-staging.example", client=client)
        result = directory.search(
            verified_staff=identity or staff(),
            staff_access_token="synthetic-staff-token",
            branch_id=target,
        )
    return result, calls


def test_staff_sees_only_minimum_client_fields():
    result, calls = lookup([client_record()])
    assert len(result) == 1
    assert result[0].full_name == "Mpho Test"
    assert not hasattr(result[0], "national_id")
    assert calls[0].url.path == "/api/v1/company-clients"
    assert calls[0].url.params["branch_id"] == str(BRANCH)
    assert calls[0].headers["X-Company-ID"] == str(COMPANY)
    assert calls[0].headers["X-Active-Role"] == "loan_officer"


@pytest.mark.parametrize("records", [
    [client_record(company=uuid4())],
    [client_record(branch=OTHER_BRANCH)],
    [client_record(branch=None)],
    [dict(client_record(), full_name="")],
    [dict(client_record(), id="not-a-uuid")],
])
def test_rejects_upstream_scope_and_shape_mismatch(records):
    with pytest.raises(StaffDirectoryUnavailable):
        lookup(records)


def test_cross_branch_request_denied_before_network():
    calls = []
    def respond(req):
        calls.append(req)
        return httpx.Response(200, json=[])
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        directory = LoanHubStaffClientDirectory(
            origin="https://loanhub-staging.example", client=client)
        with pytest.raises(StaffAccessDenied):
            directory.search(verified_staff=staff(),
                             staff_access_token="token",
                             branch_id=OTHER_BRANCH)
    assert calls == []


def test_management_can_read_other_branch():
    result, _ = lookup([client_record(branch=OTHER_BRANCH)],
                       identity=staff(role="COMPANY_ADMIN"),
                       target=OTHER_BRANCH)
    assert result[0].branch_id == OTHER_BRANCH


def test_rejects_wrong_user_role_before_network():
    with pytest.raises(StaffAccessDenied):
        lookup([], identity=staff(role="BORROWER"))


def test_rejects_upstream_denial():
    with pytest.raises(StaffDirectoryUnavailable):
        lookup({"detail": "Forbidden"}, status_code=403)


def test_rejects_duplicate_client_ids():
    record = client_record()
    with pytest.raises(StaffDirectoryUnavailable):
        lookup([record, record])
