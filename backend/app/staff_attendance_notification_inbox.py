"""Durable attendance notification receiver, independent of HTTP authentication.

Only a trusted, company-bound worker may call these methods. Recipients are
derived from the verified directory; original events are loaded from PostgreSQL.
"""
from datetime import date, datetime, time
from uuid import UUID

from .staff_authorization import VerifiedStaffIdentity
from .staff_morning_reminder import LESOTHO
from .staff_attendance_dispatch_worker import DispatchOutcome


class AttendanceNotificationInbox:
    def __init__(self, connect, directory, *, company_id):
        if not isinstance(company_id, UUID):
            raise ValueError("Explicit company required")
        self._connect = connect
        self._directory = directory
        self._company = company_id

    def _members(self):
        rows = self._directory.employees(company_id=self._company, limit=100)
        if not isinstance(rows, (tuple, list)) or len(rows) > 100:
            raise ValueError("Incomplete directory")
        result = {}
        for row in rows:
            if (not isinstance(row, VerifiedStaffIdentity)
                    or row.company_id != self._company or row.user_id in result
                    or type(row.active) is not bool):
                raise ValueError("Unverified directory")
            result[row.user_id] = row
        return result

    def _insert(self, cur, recipient, key, employee, kind, observed, expiry=None):
        cur.execute("""INSERT INTO staff_attendance_notification_inbox
            (company_id, recipient_id, idempotency_key, employee_id,
             event_type, observed_at, expires_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (company_id, recipient_id, idempotency_key) DO NOTHING""",
            (self._company, recipient, key, employee, kind, observed, expiry))

    def accept_owner_event(self, *, event_id, access, key):
        if type(access) is not bool:
            return DispatchOutcome.REJECTED
        if access:
            if not isinstance(event_id, UUID):
                return DispatchOutcome.REJECTED
            expected = f"batlokoa:access:{self._company}:{event_id}"
            query = """SELECT e.employee_id,e.event_type,e.observed_at
                FROM staff_attendance_access_events e
                JOIN staff_access_notification_delivery d ON d.event_id=e.event_id
                WHERE e.company_id=%s AND e.event_id=%s AND d.state IN ('leased','delivered')"""
        else:
            if type(event_id) is not int or not 0 < event_id < 2**63:
                return DispatchOutcome.REJECTED
            expected = f"batlokoa:attendance:{self._company}:{event_id}"
            query = """SELECT e.employee_id,e.event_type,e.observed_at
                FROM staff_attendance_monitor_outbox e
                JOIN staff_attendance_notification_delivery d ON d.alert_id=e.alert_id
                WHERE e.company_id=%s AND e.alert_id=%s AND d.state IN ('leased','delivered')"""
        if key != expected:
            return DispatchOutcome.REJECTED
        members = self._members()
        owners = [row.user_id for row in members.values()
                  if row.active is True and row.role == "COMPANY_OWNER"]
        if not owners:
            return DispatchOutcome.RECIPIENT_UNAVAILABLE
        with self._connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(query, (self._company, event_id))
                event = cur.fetchone()
                if not event:
                    return DispatchOutcome.REJECTED
                employee, kind, observed = event
                for owner in owners:
                    self._insert(cur, owner, key, employee, kind, observed)
        return DispatchOutcome.ACCEPTED

    def accept_morning(self, *, employee_id, work_date, key):
        if not isinstance(employee_id, UUID) or type(work_date) is not date:
            return DispatchOutcome.REJECTED
        if key != f"batlokoa:morning:{self._company}:{employee_id}:{work_date.isoformat()}":
            return DispatchOutcome.REJECTED
        member = self._members().get(employee_id)
        if member is None or member.active is not True or member.role not in {
                "COMPANY_OWNER", "COMPANY_ADMIN", "BRANCH_MANAGER",
                "LOAN_OFFICER", "CREDIT_ANALYST"}:
            return DispatchOutcome.REJECTED
        start = datetime.combine(work_date, time.min, tzinfo=LESOTHO)
        expiry = datetime.combine(work_date, time(7, 15), tzinfo=LESOTHO)
        with self._connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                            (f"staff-attendance:{self._company}:{employee_id}",))
                cur.execute("SELECT clock_timestamp()")
                now = cur.fetchone()[0]
                local = now.astimezone(LESOTHO)
                if local.date() != work_date or not time(7) <= local.time() < time(7, 15):
                    return DispatchOutcome.REJECTED
                cur.execute("""SELECT 1 FROM staff_morning_reminder_delivery d
                    JOIN staff_morning_work_roster r USING (company_id, employee_id, work_date)
                    WHERE d.company_id=%s AND d.employee_id=%s AND d.work_date=%s
                    AND d.state IN ('leased','delivered') AND r.scheduled_to_work IS TRUE
                    AND NOT EXISTS (SELECT 1 FROM staff_attendance_sessions a
                        WHERE a.company_id=d.company_id AND a.employee_id=d.employee_id
                        AND (a.clocked_out_at IS NULL OR a.clocked_in_at >= %s))
                    FOR SHARE OF r""", (self._company, employee_id, work_date, start))
                if not cur.fetchone():
                    return DispatchOutcome.REJECTED
                cur.execute("SELECT clock_timestamp()")
                now = cur.fetchone()[0]
                if now >= expiry:
                    return DispatchOutcome.REJECTED
                self._insert(cur, employee_id, key, employee_id, "morning_reminder", now, expiry)
        return DispatchOutcome.ACCEPTED
