"""A registration branch is always assigned by the trusted LoanHub scope."""
from types import SimpleNamespace
from uuid import uuid4
import pytest

from backend.app.staff_registration_branches_routes import _verified_branches

COMPANY, OTHER, ASSIGNED, UNASSIGNED = (uuid4() for _ in range(4))


def staff(**changes):
    args = dict(company_id=COMPANY, branch_ids=frozenset({ASSIGNED}),
                company_wide_scope=False)
    args.update(changes)
    return SimpleNamespace(**args)


def branch(id, company=COMPANY, **extra):
    data = dict(id=str(id), company_id=str(company),
                name="Maseru branch", is_active=True)
    data.update(extra)
    return data


def test_branch_names_are_sourced_only_from_authorized_membership():
    result = _verified_branches(
        [branch(ASSIGNED), branch(UNASSIGNED)], staff())
    assert result == [{"id": str(ASSIGNED), "name": "Maseru branch"}]


def test_company_owner_can_choose_any_company_branch():
    result = _verified_branches(
        [branch(ASSIGNED), branch(UNASSIGNED)],
        staff(company_wide_scope=True))
    assert len(result) == 2


def test_cross_company_branch_is_rejected_instead_of_skipped():
    with pytest.raises(ValueError):
        _verified_branches([branch(ASSIGNED, company=OTHER)], staff())


def test_inactive_branch_and_duplicate_entry_are_not_user_choices():
    assert _verified_branches([branch(ASSIGNED, is_active=False)], staff()) == []
    with pytest.raises(ValueError):
        _verified_branches([branch(ASSIGNED), branch(ASSIGNED)], staff())
