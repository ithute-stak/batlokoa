"""Candidate PostgreSQL attendance adapter; not enabled in production.

The connection factory must return a dedicated psycopg connection with
reviewed privileges. Identity and active branch must be freshly verified.
"""
from datetime import datetime, timezone

from .staff_attendance import (
    AttendanceAction, AttendanceRejected, OpenAttendance, attendance_transition,
)
from .staff_authorization import VerifiedStaffIdentity, StaffAccessDenied
from .staff_branch_location import ActiveBranch, BranchLocation
from .staff_geofence import Position


class AttendanceStore:
    def __init__(self, connect):
        self._connect = connect

    def record(self, identity, branch, sample, action, *, captured_at):
        if (not isinstance(identity, VerifiedStaffIdentity)
                or identity.active is not True
                or not isinstance(branch, ActiveBranch)
                or branch.active is not True
                or identity.company_id != branch.company_id
                or identity.role not in {"COMPANY_OWNER", "COMPANY_ADMIN",
                    "BRANCH_MANAGER", "LOAN_OFFICER", "CREDIT_ANALYST"}
                or not (branch.branch_id in identity.branch_ids
                        or (identity.company_wide_scope is True
                            and identity.role in {"COMPANY_OWNER", "COMPANY_ADMIN"}))):
            raise StaffAccessDenied("Active authorized employee required")
        if not isinstance(captured_at, datetime) or captured_at.utcoffset() is None:
            raise AttendanceRejected("LOCATION_UNVERIFIED")
        with self._connect() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    # Read committed is required so a waiter sees the previous
                    # writer's committed session after obtaining the lock.
                    cur.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                    cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                                (f"staff-attendance:{identity.company_id}:{identity.user_id}",))
                    cur.execute("""SELECT session_id, branch_id, clocked_in_at
                        FROM staff_attendance_sessions
                        WHERE company_id=%s AND employee_id=%s AND clocked_out_at IS NULL
                        FOR UPDATE""", (identity.company_id, identity.user_id))
                    row = cur.fetchone()
                    opened = None if row is None else OpenAttendance(
                        identity.company_id, identity.user_id, row[1], row[2])
                    cur.execute("""SELECT revision_id, latitude, longitude, accuracy_m,
                                          radius_m, registered_by, registered_at
                        FROM staff_branch_location_history
                        WHERE company_id=%s AND branch_id=%s
                        ORDER BY revision_id DESC LIMIT 1""",
                        (identity.company_id, branch.branch_id))
                    registered = cur.fetchone()
                    if registered is None:
                        raise AttendanceRejected("BRANCH_LOCATION_UNAVAILABLE")
                    revision, lat, lon, accuracy, radius, actor, timestamp = registered
                    location = BranchLocation(identity.company_id, branch.branch_id,
                        Position(lat, lon, accuracy), radius, actor, timestamp)
                    now = datetime.now(timezone.utc)
                    # Browser timestamp is only a freshness plausibility check.
                    age = (now - captured_at).total_seconds()
                    event = attendance_transition(
                        identity, branch, location, sample, action,
                        location_revision=revision, open_attendance=opened,
                        server_now=now, fresh=-5 <= age <= 30,
                    )
                    if action is AttendanceAction.CLOCK_IN:
                        cur.execute("""INSERT INTO staff_attendance_sessions
                            (company_id, employee_id, branch_id, clocked_in_at)
                            VALUES (%s,%s,%s,%s) RETURNING session_id""",
                            (event.company_id, event.employee_id, event.branch_id, now))
                        session_id = cur.fetchone()[0]
                    else:
                        session_id = row[0]
                        cur.execute("""UPDATE staff_attendance_sessions
                            SET clocked_out_at=%s
                            WHERE session_id=%s AND company_id=%s AND employee_id=%s
                              AND branch_id=%s AND clocked_out_at IS NULL""",
                            (now, session_id, event.company_id, event.employee_id,
                             event.branch_id))
                        if cur.rowcount != 1:
                            raise AttendanceRejected("SESSION_CHANGED")
                    cur.execute("""INSERT INTO staff_attendance_events
                        (session_id, company_id, employee_id, branch_id, action,
                         recorded_at, location_revision, location_state)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING event_id""",
                        (session_id, event.company_id, event.employee_id,
                         event.branch_id, event.action.value, event.recorded_at,
                         event.location_revision, event.location_state.value))
                    event_id = cur.fetchone()[0]
        return session_id, event_id, event


    def read_sessions(self, identity, *, open_only=False, limit=30, before=None):
        """Return only the verified employee's own sessions, including past branches."""
        if (not isinstance(identity, VerifiedStaffIdentity)
                or identity.active is not True
                or identity.role not in {"COMPANY_OWNER", "COMPANY_ADMIN",
                    "BRANCH_MANAGER", "LOAN_OFFICER", "CREDIT_ANALYST"}):
            raise StaffAccessDenied("Active authorized employee required")
        if (type(limit) is not int or not 1 <= limit <= 100
                or (before is not None and (type(before) is not int or before <= 0))):
            raise ValueError("Invalid pagination")
        query = """SELECT session_id, branch_id, clocked_in_at, clocked_out_at
            FROM staff_attendance_sessions WHERE company_id=%s AND employee_id=%s"""
        params = [identity.company_id, identity.user_id]
        if open_only:
            query += " AND clocked_out_at IS NULL"
        if before is not None:
            query += " AND session_id < %s"
            params.append(before)
        query += " ORDER BY session_id DESC LIMIT %s"
        params.append(limit)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()
        return [{"session_id": row[0], "branch_id": str(row[1]),
                 "clocked_in_at": row[2].isoformat(),
                 "clocked_out_at": row[3].isoformat() if row[3] is not None else None}
                for row in rows]
