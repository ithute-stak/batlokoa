"""Pure attendance state transitions; no automatic clocking or tracking.

All identity, active branch, current location revision and open-session data
must be loaded by the trusted server. Persistence must serialize transitions
per company/employee and atomically append the audit event.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID

from .staff_authorization import VerifiedStaffIdentity, StaffAccessDenied
from .staff_branch_location import ActiveBranch, BranchLocation, RADIUS_M
from .staff_geofence import Position, LocationState, classify


class AttendanceAction(str, Enum):
    CLOCK_IN = "clock_in"
    CLOCK_OUT = "clock_out"


class AttendanceRejected(ValueError):
    """Stable policy rejection; not a successful attendance event."""


@dataclass(frozen=True)
class OpenAttendance:
    company_id: UUID
    employee_id: UUID
    branch_id: UUID
    clocked_in_at: datetime


@dataclass(frozen=True)
class AttendanceEvent:
    company_id: UUID
    employee_id: UUID
    branch_id: UUID
    action: AttendanceAction
    recorded_at: datetime
    location_revision: int
    location_state: LocationState


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise AttendanceRejected("INVALID_SERVER_TIME")
    return value.astimezone(timezone.utc)


def attendance_transition(
    identity: VerifiedStaffIdentity,
    branch: ActiveBranch,
    location: BranchLocation,
    sample: Position,
    action: AttendanceAction,
    *,
    location_revision: int,
    open_attendance: OpenAttendance | None,
    server_now: datetime,
    fresh: bool = False,
) -> AttendanceEvent:
    if (not isinstance(identity, VerifiedStaffIdentity)
            or identity.active is not True
            or not isinstance(branch, ActiveBranch)
            or branch.active is not True
            or not isinstance(branch.branch_id, UUID)
            or identity.company_id != branch.company_id
            or identity.role not in {"COMPANY_OWNER", "COMPANY_ADMIN",
                "BRANCH_MANAGER", "LOAN_OFFICER", "CREDIT_ANALYST"}
            or not (branch.branch_id in identity.branch_ids
                    or (identity.company_wide_scope is True
                        and identity.role in {"COMPANY_OWNER", "COMPANY_ADMIN"}))):
        raise StaffAccessDenied("Active authorized staff and branch required")
    now = _utc(server_now)
    if not isinstance(action, AttendanceAction):
        raise AttendanceRejected("INVALID_ACTION")
    if (not isinstance(location, BranchLocation)
            or location.company_id != branch.company_id
            or location.branch_id != branch.branch_id
            or location.radius_m != RADIUS_M
            or type(location_revision) is not int
            or location_revision <= 0
            or not isinstance(location.position, Position)
            or not location.position.valid()
            or location.position.accuracy_m > 5
            or _utc(location.registered_at) > now):
        raise AttendanceRejected("BRANCH_LOCATION_UNAVAILABLE")
    if open_attendance is not None:
        if (not isinstance(open_attendance, OpenAttendance)
                or open_attendance.company_id != identity.company_id
                or open_attendance.employee_id != identity.user_id):
            raise StaffAccessDenied("Attendance scope mismatch")
        if _utc(open_attendance.clocked_in_at) > now:
            raise AttendanceRejected("INVALID_ATTENDANCE_TIME")
    if action is AttendanceAction.CLOCK_IN and open_attendance is not None:
        raise AttendanceRejected("ALREADY_CLOCKED_IN")
    if action is AttendanceAction.CLOCK_OUT:
        if open_attendance is None:
            raise AttendanceRejected("NOT_CLOCKED_IN")
        if open_attendance.branch_id != branch.branch_id:
            raise AttendanceRejected("CLOCK_OUT_AT_ORIGINAL_BRANCH")
    if not isinstance(sample, Position):
        raise AttendanceRejected("LOCATION_UNVERIFIED")
    state = classify(location.position, sample, radius_m=RADIUS_M,
                     fresh=fresh is True)
    if state is not LocationState.INSIDE:
        raise AttendanceRejected("OUTSIDE_PERIMETER" if state is LocationState.OUTSIDE
                                 else "LOCATION_UNVERIFIED")
    return AttendanceEvent(identity.company_id, identity.user_id,
                           branch.branch_id, action, now,
                           location_revision, state)
