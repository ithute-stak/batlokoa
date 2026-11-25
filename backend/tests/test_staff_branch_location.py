from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.staff_authorization import VerifiedStaffIdentity, StaffAccessDenied
from app.staff_branch_location import ActiveBranch, register_branch_location
from app.staff_geofence import Position


COMPANY = uuid4()
BRANCH = ActiveBranch(COMPANY, uuid4(), True)
OWNER = VerifiedStaffIdentity(uuid4(), COMPANY, "COMPANY_OWNER", True,
                              frozenset(), True)
POSITION = Position(-29.31, 27.48, 2)
NOW = datetime(2026, 11, 25, tzinfo=timezone.utc)


def register(identity=OWNER, branch=BRANCH, position=POSITION, fresh=True):
    return register_branch_location(identity, branch, position,
                                    fresh=fresh, server_now=NOW)


def test_owner_registration():
    result = register()
    assert result.company_id == COMPANY
    assert result.branch_id == BRANCH.branch_id
    assert result.registered_by == OWNER.user_id
    assert result.registered_at == NOW
    assert result.radius_m == 10
    assert result.position == POSITION


@pytest.mark.parametrize("identity", [
    None,
    replace(OWNER, active=False),
    replace(OWNER, company_id=uuid4()),
    replace(OWNER, role="COMPANY_ADMIN"),
    replace(OWNER, role="BRANCH_MANAGER"),
    replace(OWNER, role="BORROWER"),
    replace(OWNER, company_wide_scope=False),
])
def test_unauthorized_identity(identity):
    with pytest.raises(StaffAccessDenied):
        register(identity=identity)


@pytest.mark.parametrize("branch", [
    replace(BRANCH, active=False),
    replace(BRANCH, company_id=uuid4()),
])
def test_invalid_branch(branch):
    with pytest.raises(StaffAccessDenied):
        register(branch=branch)


@pytest.mark.parametrize("position", [
    Position(-29.31, 27.48, 5.01),
    Position(-29.31, 27.48, 0),
    Position(91, 27.48, 2),
])
def test_invalid_capture(position):
    with pytest.raises(ValueError):
        register(position=position)


def test_stale_capture():
    with pytest.raises(ValueError):
        register(fresh=False)


def test_naive_server_timestamp():
    with pytest.raises(ValueError):
        register_branch_location(OWNER, BRANCH, POSITION, fresh=True,
                                 server_now=NOW.replace(tzinfo=None))
