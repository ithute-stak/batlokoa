"""Explicit owner-managed shifts; no implicit working hours."""
from datetime import date, datetime, timedelta

from .staff_authorization import StaffAccessDenied, VerifiedStaffIdentity
from .staff_morning_work_roster_store import MorningWorkRosterStore
from .staff_morning_reminder import LESOTHO


class WorkShiftStore:
    def __init__(self, connect):
        self._connect = connect

    def set_shift(self, actor, employee, *, work_date, starts_at, ends_at, grace_minutes):
        MorningWorkRosterStore._owner(actor)
        if (not isinstance(employee, VerifiedStaffIdentity)
                or employee.company_id != actor.company_id
                or employee.active is not True
                or employee.role not in {"COMPANY_OWNER", "COMPANY_ADMIN",
                    "BRANCH_MANAGER", "LOAN_OFFICER", "CREDIT_ANALYST"}):
            raise StaffAccessDenied("Verified active same-company employee required")
        if (type(work_date) is not date or type(grace_minutes) is not int
                or not 0 <= grace_minutes <= 120
                or any(not isinstance(t, datetime) or t.utcoffset() is None
                       for t in (starts_at, ends_at))):
            raise ValueError("Invalid shift settings")
        if (starts_at.astimezone(LESOTHO).date() != work_date
                or not timedelta(minutes=grace_minutes) < ends_at - starts_at
                       <= timedelta(hours=24)):
            raise ValueError("Invalid shift interval")
        with self._connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute("SELECT (clock_timestamp() AT TIME ZONE 'Africa/Maseru')::date")
                today = cur.fetchone()[0]
                if not today <= work_date <= today + timedelta(days=366):
                    raise ValueError("Shift outside scheduling horizon")
                cur.execute("""SELECT scheduled_to_work FROM staff_morning_work_roster
                    WHERE company_id=%s AND employee_id=%s AND work_date=%s FOR UPDATE""",
                    (actor.company_id, employee.user_id, work_date))
                row = cur.fetchone()
                if row is None or row[0] is not True:
                    raise ValueError("Explicit working day required")
                cur.execute("""INSERT INTO staff_work_shifts
                    (company_id, employee_id, work_date, starts_at, ends_at,
                     grace_minutes, recorded_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (company_id, employee_id, work_date) DO UPDATE
                    SET starts_at=EXCLUDED.starts_at, ends_at=EXCLUDED.ends_at,
                        grace_minutes=EXCLUDED.grace_minutes,
                        recorded_by=EXCLUDED.recorded_by, recorded_at=clock_timestamp()
                    WHERE (staff_work_shifts.starts_at, staff_work_shifts.ends_at,
                           staff_work_shifts.grace_minutes) IS DISTINCT FROM
                          (EXCLUDED.starts_at, EXCLUDED.ends_at, EXCLUDED.grace_minutes)""",
                    (actor.company_id, employee.user_id, work_date, starts_at,
                     ends_at, grace_minutes, actor.user_id))
                return cur.rowcount == 1

    def read_day(self, actor, *, work_date, after=None, limit=50):
        from uuid import UUID
        MorningWorkRosterStore._owner(actor)
        if (type(work_date) is not date or type(limit) is not int
                or not 1 <= limit <= 100
                or (after is not None and not isinstance(after, UUID))):
            raise ValueError("Invalid shift pagination")
        query = """SELECT s.employee_id, s.starts_at, s.ends_at, s.grace_minutes
            FROM staff_work_shifts s JOIN staff_morning_work_roster r
            USING (company_id, employee_id, work_date)
            WHERE s.company_id=%s AND s.work_date=%s AND r.scheduled_to_work IS TRUE"""
        params = [actor.company_id, work_date]
        if after is not None:
            query += " AND s.employee_id>%s"
            params.append(after)
        query += " ORDER BY s.employee_id LIMIT %s"
        params.append(limit+1)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()
        page = rows[:limit]
        return {"rows": [{"employee_id": str(r[0]), "starts_at": r[1].isoformat(),
                          "ends_at": r[2].isoformat(), "grace_minutes": r[3]}
                         for r in page],
                "next_after": str(page[-1][0]) if len(rows)>limit else None}
