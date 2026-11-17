"""Network-free authorization regression tests for Batlokoa employee portal."""
from dataclasses import replace
from uuid import uuid4

import pytest

from backend.app.staff_authorization import (
    StaffAccessDenied,
    StaffPermission,
    VerifiedStaffIdentity,
    require_staff_permission,
)

COMPANY = uuid4()
OTHER_COMPANY = uuid4()
BRANCH = uuid4()
OTHER_BRANCH = uuid4()


def staff(**kwargs):
    values = dict(
        user_id=uuid4(),
        company_id=COMPANY,
        role="LOAN_OFFICER",
        active=True,
        branch_ids=frozenset({BRANCH}),
    )
    values.update(kwargs)
    return VerifiedStaffIdentity(**values)


@pytest.mark.parametrize("permission", list(StaffPermission))
def test_assigned_active_lending_staff_can_access_scoped_operations(permission):
    require_staff_permission(staff(), expected_company_id=COMPANY,
                             branch_id=BRANCH, permission=permission)


@pytest.mark.parametrize("identity", [
    None,
    staff(active=False),
    staff(company_id=OTHER_COMPANY),
    staff(role="BORROWER"),
    staff(role="CASHIER"),
    staff(branch_ids=frozenset()),
    staff(branch_ids=frozenset({OTHER_BRANCH})),
    staff(role="BRANCH_MANAGER", company_wide_scope=True),
])
def test_denies_unverified_inactive_cross_tenant_or_cross_branch(identity):
    with pytest.raises(StaffAccessDenied):
        require_staff_permission(identity, expected_company_id=COMPANY,
                                 branch_id=BRANCH,
                                 permission=StaffPermission.REGISTER_CLIENT)


def test_management_can_use_verified_company_wide_scope():
    require_staff_permission(
        staff(role="COMPANY_ADMIN", branch_ids=frozenset(),
              company_wide_scope=True),
        expected_company_id=COMPANY, branch_id=OTHER_BRANCH,
        permission=StaffPermission.PREPARE_OFFER,
    )


def test_management_without_company_wide_grant_still_requires_branch():
    with pytest.raises(StaffAccessDenied):
        require_staff_permission(
            staff(role="COMPANY_ADMIN", branch_ids=frozenset()),
            expected_company_id=COMPANY, branch_id=OTHER_BRANCH,
            permission=StaffPermission.CREATE_APPLICATION,
        )


def test_rejects_malformed_branch_assignments():
    with pytest.raises(ValueError):
        staff(branch_ids=frozenset({"branch-as-text"}))


def test_never_includes_disbursement_or_approval_permission():
    assert not any("disburse" in p.value or "approve" in p.value
                   for p in StaffPermission)
