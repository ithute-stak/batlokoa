from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from backend.app.staff_attendance import (
    AttendanceAction, AttendanceRejected, OpenAttendance, attendance_transition,
)
from backend.app.staff_authorization import VerifiedStaffIdentity, StaffAccessDenied
from backend.app.staff_branch_location import ActiveBranch, BranchLocation
from backend.app.staff_geofence import Position, LocationState


@pytest.fixture
def context():
    now = datetime.now(timezone.utc)
    company, branch_id, employee = uuid4(), uuid4(), uuid4()
    identity = VerifiedStaffIdentity(employee, company, "LOAN_OFFICER", True,
                                     frozenset({branch_id}))
    branch = ActiveBranch(company, branch_id, True)
    position = Position(-29.31, 27.48, 2)
    location = BranchLocation(company, branch_id, position, 10, uuid4(),
                              now - timedelta(days=1))
    return identity, branch, location, position, now


def transition(context, action=AttendanceAction.CLOCK_IN, **changes):
    identity, branch, location, sample, now = context
    args = dict(identity=identity, branch=branch, location=location,
                sample=sample, action=action, location_revision=1,
                open_attendance=None, server_now=now, fresh=True)
    args.update(changes)
    return attendance_transition(**args)


def test_clock_in_and_out(context):
    identity, branch, _, _, now = context
    event = transition(context)
    assert event.employee_id == identity.user_id
    assert event.location_state is LocationState.INSIDE
    assert event.recorded_at == now
    session = OpenAttendance(identity.company_id, identity.user_id,
                             branch.branch_id, now)
    out = transition(context, AttendanceAction.CLOCK_OUT,
                     open_attendance=session, server_now=now + timedelta(hours=8))
    assert out.action is AttendanceAction.CLOCK_OUT


def test_duplicate_and_missing_session(context):
    identity, branch, _, _, now = context
    session = OpenAttendance(identity.company_id, identity.user_id,
                             branch.branch_id, now)
    with pytest.raises(AttendanceRejected, match="ALREADY_CLOCKED_IN"):
        transition(context, open_attendance=session)
    with pytest.raises(AttendanceRejected, match="NOT_CLOCKED_IN"):
        transition(context, AttendanceAction.CLOCK_OUT)
    with pytest.raises(AttendanceRejected, match="CLOCK_OUT_AT_ORIGINAL_BRANCH"):
        transition(context, AttendanceAction.CLOCK_OUT,
                   open_attendance=replace(session, branch_id=uuid4()))


@pytest.mark.parametrize("sample,fresh,code", [
    (Position(-29.32, 27.48, 2), True, "OUTSIDE_PERIMETER"),
    (Position(-29.31, 27.48, 12), True, "LOCATION_UNVERIFIED"),
    (Position(-29.31, 27.48, 2), False, "LOCATION_UNVERIFIED"),
    (Position(-29.31008, 27.48, 2), True, "LOCATION_UNVERIFIED"),
])
@pytest.mark.parametrize("action", list(AttendanceAction))
def test_location_rejected(context, sample, fresh, code, action):
    identity, branch, _, _, now = context
    session = (OpenAttendance(identity.company_id, identity.user_id,
                              branch.branch_id, now)
               if action is AttendanceAction.CLOCK_OUT else None)
    with pytest.raises(AttendanceRejected, match=code):
        transition(context, action, sample=sample, fresh=fresh,
                   open_attendance=session)


def test_authorization_and_revision(context):
    identity, branch, location, _, _ = context
    for unauthorized in (replace(identity, active=False),
                         replace(identity, company_id=uuid4()),
                         replace(identity, branch_ids=frozenset())):
        with pytest.raises(StaffAccessDenied):
            transition(context, identity=unauthorized)
    with pytest.raises(StaffAccessDenied):
        transition(context, branch=replace(branch, active=False))
    with pytest.raises(AttendanceRejected, match="BRANCH_LOCATION_UNAVAILABLE"):
        transition(context, location=replace(location, branch_id=uuid4()))
    with pytest.raises(AttendanceRejected, match="BRANCH_LOCATION_UNAVAILABLE"):
        transition(context, location_revision=0)
