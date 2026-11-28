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


    def read_notifications(self, identity, *, limit=50, before_at=None, before_key=None):
        from .staff_authorization import StaffAccessDenied
        if (not isinstance(identity, VerifiedStaffIdentity)
                or identity.company_id != self._company or identity.active is not True
                or identity.role not in {"COMPANY_OWNER", "COMPANY_ADMIN", "BRANCH_MANAGER",
                                         "LOAN_OFFICER", "CREDIT_ANALYST"}):
            raise StaffAccessDenied("Verified active recipient required")
        if (type(limit) is not int or not 1 <= limit <= 100
                or (before_at is None) != (before_key is None)
                or (before_at is not None and (not isinstance(before_at, datetime)
                    or before_at.utcoffset() is None or not isinstance(before_key, str)
                    or not 1 <= len(before_key) <= 200))):
            raise ValueError("Invalid inbox pagination")
        # Former owners must not retain access to owner-only notifications.
        owner = identity.role == "COMPANY_OWNER" and identity.company_wide_scope is True
        query = """SELECT idempotency_key, employee_id, event_type, observed_at,
                       created_at, expires_at, read_at
                    FROM staff_attendance_notification_inbox
                    WHERE company_id=%s AND recipient_id=%s
                      AND (expires_at IS NULL OR expires_at>clock_timestamp())
                      AND (%s OR event_type='morning_reminder')"""
        params = [self._company, identity.user_id, owner]
        if before_at is not None:
            query += " AND (created_at,idempotency_key)<(%s,%s)"
            params.extend([before_at, before_key])
        query += " ORDER BY created_at DESC,idempotency_key DESC LIMIT %s"
        params.append(limit+1)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()
        page = rows[:limit]
        return {"notifications": [
            {"key": row[0], "employee_id": str(row[1]), "event_type": row[2],
             "observed_at": row[3].isoformat(), "created_at": row[4].isoformat(),
             "expires_at": row[5].isoformat() if row[5] else None,
             "read_at": row[6].isoformat() if row[6] else None}
            for row in page],
            "next_before": {"created_at": page[-1][4].isoformat(), "key": page[-1][0]}
                if len(rows)>limit else None}
