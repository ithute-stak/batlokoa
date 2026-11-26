"""Persistent morning reminder enqueue service; no live scheduler.

The caller supplies a freshly verified company roster candidate. Database time
and attendance records independently constrain enqueue; a dispatch worker must
revalidate roster and attendance before sending.
"""
from dataclasses import dataclass
from datetime import date, datetime, time
from uuid import UUID, uuid4

from .staff_morning_reminder import LESOTHO, reminder_key


@dataclass(frozen=True)
class MorningReminderClaim:
    company_id: UUID
    employee_id: UUID
    work_date: date
    lease_token: UUID
    attempts: int

    @property
    def idempotency_key(self):
        return f"batlokoa:morning:{self.company_id}:{self.employee_id}:{self.work_date.isoformat()}"


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

    def claim(self):
        """Lease one eligible-time row; never reclaim outside today's window."""
        with self._connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute("""UPDATE staff_morning_reminder_delivery
                    SET state='cancelled', lease_token=NULL, lease_until=NULL,
                        last_error_code='window_closed'
                    WHERE company_id=%s
                      AND (state='pending' OR (state='leased' AND lease_until <= clock_timestamp()))
                      AND (work_date < (clock_timestamp() AT TIME ZONE 'Africa/Maseru')::date
                        OR (work_date = (clock_timestamp() AT TIME ZONE 'Africa/Maseru')::date
                            AND (clock_timestamp() AT TIME ZONE 'Africa/Maseru')::time >= TIME '07:15'))""",
                    (self._company_id,))
                cur.execute("""UPDATE staff_morning_reminder_delivery
                    SET state='dead', lease_token=NULL, lease_until=NULL,
                        last_error_code='lease_expired'
                    WHERE company_id=%s AND state='leased'
                      AND attempts=10 AND lease_until <= clock_timestamp()""", (self._company_id,))
                cur.execute("""WITH candidate AS (
                    SELECT company_id, employee_id, work_date
                    FROM staff_morning_reminder_delivery
                    WHERE company_id=%s
                      AND work_date=(clock_timestamp() AT TIME ZONE 'Africa/Maseru')::date
                      AND (clock_timestamp() AT TIME ZONE 'Africa/Maseru')::time >= TIME '07:00'
                      AND (clock_timestamp() AT TIME ZONE 'Africa/Maseru')::time < TIME '07:15'
                      AND attempts<10
                      AND ((state='pending' AND available_at<=clock_timestamp())
                        OR (state='leased' AND lease_until<=clock_timestamp()))
                    ORDER BY available_at, employee_id
                    LIMIT 1 FOR UPDATE SKIP LOCKED)
                    UPDATE staff_morning_reminder_delivery d
                    SET state='leased', attempts=d.attempts+1, lease_token=%s,
                        lease_until=clock_timestamp()+interval '120 seconds'
                    FROM candidate c
                    WHERE d.company_id=c.company_id AND d.employee_id=c.employee_id
                      AND d.work_date=c.work_date
                    RETURNING d.company_id,d.employee_id,d.work_date,d.lease_token,d.attempts""",
                    (self._company_id, uuid4()))
                row = cur.fetchone()
                return MorningReminderClaim(*row) if row else None

    def _scope(self, claim):
        if not isinstance(claim, MorningReminderClaim) or claim.company_id != self._company_id:
            raise ValueError("Claim outside company scope")
        return claim.company_id, claim.employee_id, claim.work_date, claim.lease_token

    def ready(self, claim, candidate):
        """Recheck fresh roster and actual attendance; does not hold a lock during send."""
        scope = self._scope(claim)
        with self._connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                            (f"staff-attendance:{claim.company_id}:{claim.employee_id}",))
                cur.execute("SELECT clock_timestamp()")
                now = cur.fetchone()[0]
                if (candidate is None
                        or reminder_key(candidate, company_id=self._company_id, now=now)
                           != claim.idempotency_key):
                    return False
                start = datetime.combine(claim.work_date, time.min, tzinfo=LESOTHO)
                cur.execute("""SELECT EXISTS (
                    SELECT 1 FROM staff_morning_reminder_delivery
                    WHERE company_id=%s AND employee_id=%s AND work_date=%s AND lease_token=%s
                      AND state='leased' AND lease_until>clock_timestamp()
                      AND (clock_timestamp() AT TIME ZONE 'Africa/Maseru')::time < TIME '07:15'
                    ) AND NOT EXISTS (
                    SELECT 1 FROM staff_attendance_sessions
                    WHERE company_id=%s AND employee_id=%s
                      AND (clocked_out_at IS NULL OR clocked_in_at >= %s))""",
                    (*scope, claim.company_id, claim.employee_id, start))
                return cur.fetchone()[0] is True

    def acknowledge(self, claim):
        with self._connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute("""UPDATE staff_morning_reminder_delivery
                    SET state='delivered', delivered_at=clock_timestamp(),
                        lease_token=NULL, lease_until=NULL, last_error_code=NULL
                    WHERE company_id=%s AND employee_id=%s AND work_date=%s AND lease_token=%s
                      AND state='leased' AND lease_until>clock_timestamp()""", self._scope(claim))
                return cur.rowcount == 1

    def fail(self, claim, *, code, permanent=False):
        if code not in {"provider_unavailable", "recipient_unavailable", "provider_rejected",
                        "eligibility_unverified", "no_longer_eligible", "window_closed"}:
            raise ValueError("Invalid sanitized failure code")
        if type(permanent) is not bool:
            raise ValueError("Invalid permanent flag")
        with self._connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute("""UPDATE staff_morning_reminder_delivery
                    SET state=CASE WHEN %s IN ('no_longer_eligible','window_closed') THEN 'cancelled'
                                   WHEN %s OR attempts>=10 THEN 'dead' ELSE 'pending' END,
                        available_at=clock_timestamp()+LEAST(3600,30*power(2,attempts-1))*interval '1 second',
                        lease_token=NULL, lease_until=NULL, last_error_code=%s
                    WHERE company_id=%s AND employee_id=%s AND work_date=%s AND lease_token=%s
                      AND state='leased' AND lease_until>clock_timestamp()""",
                    (code, permanent, code, *self._scope(claim)))
                return cur.rowcount == 1
