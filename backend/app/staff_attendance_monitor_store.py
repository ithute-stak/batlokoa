"""Candidate transactional monitoring adapter; no automatic activation.

Identity and active branch must be freshly verified by the calling boundary.
Only active attendance sessions are monitored; raw samples are not retained.
"""
from datetime import datetime, timezone
from uuid import UUID

from .staff_attendance import AttendanceRejected
from .staff_attendance_monitor import MonitorState, observe
from .staff_authorization import VerifiedStaffIdentity, StaffAccessDenied
from .staff_branch_location import ActiveBranch, RADIUS_M
from .staff_geofence import Position, LocationState, classify


class AttendanceMonitorStore:
    def __init__(self, connect):
        self._connect = connect

    def record(self, identity, branch, session_id, sample, *, captured_at):
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
            raise StaffAccessDenied("Active authorized employee required")
        if (type(session_id) is not int or not 0 < session_id <= 9223372036854775807
                or not isinstance(sample, Position) or not sample.valid()
                or not isinstance(captured_at, datetime) or captured_at.utcoffset() is None):
            raise AttendanceRejected("LOCATION_UNVERIFIED")
        scope = (session_id, identity.company_id, identity.user_id, branch.branch_id)
        with self._connect() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                    cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                                (f"staff-attendance:{identity.company_id}:{identity.user_id}",))
                    cur.execute("""SELECT clocked_in_at FROM staff_attendance_sessions
                        WHERE session_id=%s AND company_id=%s AND employee_id=%s
                          AND branch_id=%s AND clocked_out_at IS NULL FOR UPDATE""", scope)
                    opened = cur.fetchone()
                    if opened is None:
                        raise AttendanceRejected("NO_ACTIVE_SESSION")
                    cur.execute("""SELECT revision_id, latitude, longitude, accuracy_m,
                                          radius_m, registered_at
                        FROM staff_branch_location_history
                        WHERE company_id=%s AND branch_id=%s
                        ORDER BY revision_id DESC LIMIT 1""",
                        (identity.company_id, branch.branch_id))
                    registered = cur.fetchone()
                    if registered is None:
                        raise AttendanceRejected("BRANCH_LOCATION_UNAVAILABLE")
                    revision, lat, lon, accuracy, radius, registered_at = registered
                    origin = Position(lat, lon, accuracy)
                    now = datetime.now(timezone.utc)
                    if (radius != RADIUS_M or not origin.valid() or accuracy > 5
                            or registered_at > now):
                        raise AttendanceRejected("BRANCH_LOCATION_UNAVAILABLE")
                    age = (now - captured_at).total_seconds()
                    if not -5 <= age <= 30 or captured_at < opened[0]:
                        raise AttendanceRejected("LOCATION_UNVERIFIED")
                    cur.execute("""SELECT location_revision, last_observed_at,
                        last_captured_at, last_confirmed, candidate_since,
                        candidate, transition_sequence
                        FROM staff_attendance_monitor_state
                        WHERE session_id=%s AND company_id=%s AND employee_id=%s
                          AND branch_id=%s FOR UPDATE""", scope)
                    row = cur.fetchone()
                    state = MonitorState()
                    sequence = 0
                    if row is not None:
                        old_revision, last, last_capture, confirmed, since, candidate, sequence = row
                        if captured_at <= last_capture:
                            raise AttendanceRejected("LOCATION_REPLAYED")
                        # A new office location invalidates any pending transition.
                        # Preserve the last confirmed state and notification sequence.
                        state = MonitorState(last, LocationState(confirmed),
                            since if old_revision == revision else None,
                            LocationState(candidate) if candidate and old_revision == revision else None)
                    reading = classify(origin, sample, radius_m=RADIUS_M, fresh=True)
                    updated, alert = observe(state, reading, server_now=now)
                    sequence += int(alert is not None)
                    cur.execute("""INSERT INTO staff_attendance_monitor_state
                        (session_id, company_id, employee_id, branch_id, location_revision,
                         last_observed_at, last_captured_at, last_confirmed, candidate_since,
                         candidate, transition_sequence)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (session_id) DO UPDATE SET
                          location_revision=EXCLUDED.location_revision,
                          last_observed_at=EXCLUDED.last_observed_at,
                          last_captured_at=EXCLUDED.last_captured_at,
                          last_confirmed=EXCLUDED.last_confirmed,
                          candidate_since=EXCLUDED.candidate_since,
                          candidate=EXCLUDED.candidate,
                          transition_sequence=EXCLUDED.transition_sequence
                        WHERE staff_attendance_monitor_state.company_id=EXCLUDED.company_id
                          AND staff_attendance_monitor_state.employee_id=EXCLUDED.employee_id
                          AND staff_attendance_monitor_state.branch_id=EXCLUDED.branch_id""",
                        (*scope, revision, now, captured_at, updated.last_confirmed.value,
                         updated.candidate_since,
                         updated.candidate.value if updated.candidate else None, sequence))
                    if cur.rowcount != 1:
                        raise AttendanceRejected("MONITOR_SCOPE_CHANGED")
                    if alert is not None:
                        cur.execute("""INSERT INTO staff_attendance_monitor_outbox
                            (session_id, company_id, employee_id, branch_id, location_revision,
                             transition_sequence, event_type, observed_at)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (*scope, revision, sequence, alert.value, now))
        return reading, updated, alert
