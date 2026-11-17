from dataclasses import replace
from datetime import date
from uuid import uuid4

import pytest

from backend.app.staff_authorization import StaffAccessDenied, VerifiedStaffIdentity
from backend.app.staff_client_registration import (
    ClientRegistrationDraft, prepare_client_registration,
)

COMPANY, BRANCH, OTHER, STAFF = (uuid4() for _ in range(4))


def identity(**changes):
    data = dict(user_id=STAFF, company_id=COMPANY, role="LOAN_OFFICER",
                active=True, branch_ids=frozenset({BRANCH}))
    data.update(changes)
    return VerifiedStaffIdentity(**data)


def draft(**changes):
    data = dict(first_name="Palesa", last_name="Mokoena", phone="59000000",
                date_of_birth=date(1990, 1, 1), gender="female",
                district="Maseru", employment_status="employed",
                branch_id=BRANCH, national_id="example-synthetic-id",
                monthly_income="1250.00")
    data.update(changes)
    return ClientRegistrationDraft(**data)


def test_valid_draft_never_grants_permission_to_submit():
    result = prepare_client_registration(staff=identity(), draft=draft())
    assert result.company_id == COMPANY
    assert result.branch_id == BRANCH
    assert result.employee_id == STAFF
    assert result.identity_review_required
    assert result.can_submit is False
    assert "example-synthetic-id" not in str(result)


@pytest.mark.parametrize("change", [
    {"phone": "2"}, {"first_name": ""},
    {"date_of_birth": date.today()},
    {"national_id": None, "passport_number": None},
    {"monthly_income": "-1"},
    {"monthly_income": "NaN"},
    {"monthly_income": "1.001"},
    {"consent_to_credit_checks": "yes"},
])
def test_invalid_draft_fails_validation(change):
    with pytest.raises(ValueError):
        prepare_client_registration(staff=identity(), draft=draft(**change))


def test_branch_escape_denied():
    with pytest.raises(StaffAccessDenied):
        prepare_client_registration(staff=identity(), draft=draft(branch_id=OTHER))


def test_borrower_and_inactive_staff_denied():
    for state in (identity(role="BORROWER"), identity(active=False)):
        with pytest.raises(StaffAccessDenied):
            prepare_client_registration(staff=state, draft=draft())
