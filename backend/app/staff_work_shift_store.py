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


    def read_punctuality(self, actor, *, work_date, after=None, limit=50):
        """Classify explicit roster rows using one database snapshot and cutoff.

        Only clock-ins during the shift's calendar day (or overnight interval)
        count. Unknown shift settings remain unknown. Missing clock-ins are
        never proof of physical absence.
        """
        from uuid import UUID
        from .staff_attendance_reporting_policy import classify_attendance

        MorningWorkRosterStore._owner(actor)
        if (type(work_date) is not date or type(limit) is not int
                or not 1 <= limit <= 100
                or (after is not None and not isinstance(after, UUID))):
            raise ValueError("Invalid punctuality pagination")
        query = """SELECT r.employee_id, r.scheduled_to_work,
            s.starts_at, s.ends_at, s.grace_minutes, a.first_clock_in,
            statement_timestamp()
            FROM staff_morning_work_roster r
            LEFT JOIN staff_work_shifts s USING (company_id, employee_id, work_date)
            LEFT JOIN LATERAL (
                SELECT MIN(x.clocked_in_at) AS first_clock_in
                FROM staff_attendance_sessions x
                WHERE x.company_id=r.company_id AND x.employee_id=r.employee_id
                  AND x.clocked_in_at >= (r.work_date::timestamp AT TIME ZONE 'Africa/Maseru')
                  AND x.clocked_in_at < s.ends_at
                  AND x.clocked_in_at <= statement_timestamp()
            ) a ON TRUE
            WHERE r.company_id=%s AND r.work_date=%s"""
        params = [actor.company_id, work_date]
        if after is not None:
            query += " AND r.employee_id>%s"
            params.append(after)
        query += " ORDER BY r.employee_id LIMIT %s"
        params.append(limit + 1)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()
        page = rows[:limit]
        result = []
        for employee, working, start, end, grace, first, cutoff in page:
            status = classify_attendance(scheduled_to_work=working,
                shift_start=start, shift_end=end, first_clock_in=first,
                as_of=cutoff, records_complete=True,
                grace_minutes=grace if grace is not None else 0)
            late_seconds = None
            if status in {"late", "on_time"}:
                late_seconds = max(0, int((first - start).total_seconds()))
            result.append({"employee_id": str(employee), "status": status,
                "starts_at": start.isoformat() if start else None,
                "ends_at": end.isoformat() if end else None,
                "first_clock_in": first.isoformat() if first else None,
                "grace_minutes": grace, "seconds_after_scheduled_start": late_seconds,
                "as_of": cutoff.isoformat()})
        return {"rows": result, "work_date": work_date.isoformat(),
                "next_after": str(page[-1][0]) if len(rows) > limit else None}
