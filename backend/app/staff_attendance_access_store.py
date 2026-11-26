"""Candidate access audit store. Call only from verified auth boundaries.

No GPS samples, credentials or session cookies are persisted. This module
records device-reported evidence, not independently attested presence.
"""
from datetime import datetime, timezone
from uuid import UUID

from .staff_authorization import VerifiedStaffIdentity, StaffAccessDenied
from .staff_branch_location import ActiveBranch, RADIUS_M
from .staff_geofence import Position, LocationState, classify


class AttendanceAccessStore:
    def __init__(self, connect):
        self._connect = connect

    @staticmethod
    def _authorize(identity, event_id):
        if (not isinstance(identity, VerifiedStaffIdentity)
                or identity.active is not True
                or identity.role not in {"COMPANY_OWNER", "COMPANY_ADMIN",
                    "BRANCH_MANAGER", "LOAN_OFFICER", "CREDIT_ANALYST"}
                or not isinstance(event_id, UUID)):
            raise StaffAccessDenied("Verified staff access event required")

    @staticmethod
    def _insert(cur, identity, event_id, branch_id, event_type, revision):
        cur.execute("""INSERT INTO staff_attendance_access_events
            (event_id, company_id, employee_id, branch_id, event_type, location_revision)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (event_id) DO NOTHING""",
            (event_id, identity.company_id, identity.user_id, branch_id,
             event_type, revision))
        if cur.rowcount == 1:
            return True
        cur.execute("""SELECT company_id, employee_id, branch_id, event_type, location_revision
            FROM staff_attendance_access_events WHERE event_id=%s""", (event_id,))
        if cur.fetchone() != (identity.company_id, identity.user_id, branch_id, event_type, revision):
            raise StaffAccessDenied("Access event identity conflict")
        return False

    def record_login(self, identity, event_id, branch, sample, *, captured_at):
        self._authorize(identity, event_id)
        if (not isinstance(branch, ActiveBranch) or branch.active is not True
                or branch.company_id != identity.company_id
                or not (branch.branch_id in identity.branch_ids
                    or (identity.company_wide_scope is True
                        and identity.role in {"COMPANY_OWNER", "COMPANY_ADMIN"}))):
            raise StaffAccessDenied("Authorized active branch required")
        if (not isinstance(sample, Position) or not sample.valid()
                or not isinstance(captured_at, datetime)
                or captured_at.utcoffset() is None):
            return LocationState.UNVERIFIED, False
        with self._connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute("""SELECT revision_id, latitude, longitude, accuracy_m,
                    radius_m, registered_at FROM staff_branch_location_history
                    WHERE company_id=%s AND branch_id=%s
                    ORDER BY revision_id DESC LIMIT 1""",
                    (identity.company_id, branch.branch_id))
                row = cur.fetchone()
                now = datetime.now(timezone.utc)
                if row is None or not -5 <= (now-captured_at).total_seconds() <= 30:
                    return LocationState.UNVERIFIED, False
                revision, lat, lon, accuracy, radius, registered = row
                origin = Position(lat, lon, accuracy)
                if radius != RADIUS_M or not origin.valid() or accuracy > 5 or registered > now:
                    return LocationState.UNVERIFIED, False
                reading = classify(origin, sample, radius_m=RADIUS_M, fresh=True)
                if reading is not LocationState.OUTSIDE:
                    return reading, False
                created = self._insert(cur, identity, event_id, branch.branch_id,
                                       "reported_login_outside", revision)
                return reading, created

    def record_logout(self, identity, event_id):
        self._authorize(identity, event_id)
        # Do not infer a branch for a company-wide or multi-branch account.
        branch_id = next(iter(identity.branch_ids)) if len(identity.branch_ids) == 1 else None
        with self._connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                return self._insert(cur, identity, event_id, branch_id,
                                    "staff_logged_out", None)
