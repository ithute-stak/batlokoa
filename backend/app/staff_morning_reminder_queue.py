"""Persistent morning reminder enqueue service; no live scheduler.

The caller supplies a freshly verified company roster candidate. Database time
and attendance records independently constrain enqueue; a dispatch worker must
revalidate roster and attendance before sending.
"""
from datetime import datetime, time
from uuid import UUID

from .staff_morning_reminder import LESOTHO, reminder_key


class MorningReminderQueue:
    def __init__(self, connect, *, company_id):
        if not isinstance(company_id, UUID):
            raise ValueError("Explicit company required")
        self._connect = connect
        self._company_id = company_id

    def enqueue(self, candidate):
        """Return True only when a new eligible daily row is committed."""
        with self._connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                cur.execute("SELECT clock_timestamp()")
                now = cur.fetchone()[0]
                if reminder_key(candidate, company_id=self._company_id, now=now) is None:
                    return False
                cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                            (f"staff-attendance:{self._company_id}:{candidate.employee_id}",))
                # Re-read time after obtaining the attendance writer's lock.
                cur.execute("SELECT clock_timestamp()")
                now = cur.fetchone()[0]
                if reminder_key(candidate, company_id=self._company_id, now=now) is None:
                    return False
                start = datetime.combine(candidate.work_date, time.min, tzinfo=LESOTHO)
                # Count any clock-in today, even if the employee subsequently
                # clocked out, and any still-open overnight attendance session.
                cur.execute("""INSERT INTO staff_morning_reminder_delivery
                    (company_id, employee_id, work_date, created_at, available_at)
                    SELECT %s,%s,%s,%s,%s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM staff_attendance_sessions
                        WHERE company_id=%s AND employee_id=%s
                          AND (clocked_out_at IS NULL OR clocked_in_at >= %s))
                    ON CONFLICT (company_id, employee_id, work_date) DO NOTHING""",
                    (self._company_id, candidate.employee_id, candidate.work_date,
                     now, now, self._company_id, candidate.employee_id, start))
                return cur.rowcount == 1
