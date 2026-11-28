"""Owner-authorized explicit daily roster storage; not exposed by HTTP yet.

Both actor and target identities must come from fresh trusted membership
verification, not caller-supplied request fields.
"""
from datetime import date, timedelta

from .staff_authorization import StaffAccessDenied, VerifiedStaffIdentity


class MorningWorkRosterStore:
    def __init__(self, connect):
        self._connect = connect

    @staticmethod
    def _owner(actor):
        if (not isinstance(actor, VerifiedStaffIdentity)
                or actor.active is not True or actor.role != "COMPANY_OWNER"
                or actor.company_wide_scope is not True):
            raise StaffAccessDenied("Verified company-wide owner required")

    def set_day(self, actor, employee, *, work_date, scheduled_to_work):
        self._owner(actor)
        if (not isinstance(employee, VerifiedStaffIdentity)
                or employee.company_id != actor.company_id
                or employee.active is not True
                or employee.role not in {"COMPANY_OWNER", "COMPANY_ADMIN",
                    "BRANCH_MANAGER", "LOAN_OFFICER", "CREDIT_ANALYST"}):
            raise StaffAccessDenied("Verified active same-company employee required")
        if type(work_date) is not date or type(scheduled_to_work) is not bool:
            raise ValueError("Explicit working date and schedule required")
        with self._connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute("SELECT (clock_timestamp() AT TIME ZONE 'Africa/Maseru')::date")
                today = cur.fetchone()[0]
                if not today <= work_date <= today + timedelta(days=366):
                    raise ValueError("Working date outside scheduling horizon")
                cur.execute("""INSERT INTO staff_morning_work_roster
                    (company_id, employee_id, work_date, scheduled_to_work, recorded_by)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (company_id, employee_id, work_date) DO UPDATE
                    SET scheduled_to_work=EXCLUDED.scheduled_to_work,
                        recorded_by=EXCLUDED.recorded_by, recorded_at=clock_timestamp()
                    WHERE staff_morning_work_roster.scheduled_to_work
                          IS DISTINCT FROM EXCLUDED.scheduled_to_work""",
                    (actor.company_id, employee.user_id, work_date,
                     scheduled_to_work, actor.user_id))
                return cur.rowcount == 1

    def read_day(self, actor, *, work_date, after=None, limit=50):
        from uuid import UUID
        self._owner(actor)
        if (type(work_date) is not date or type(limit) is not int
                or not 1 <= limit <= 100
                or (after is not None and not isinstance(after, UUID))):
            raise ValueError("Invalid roster pagination")
        query = """SELECT employee_id, scheduled_to_work, recorded_by, recorded_at
            FROM staff_morning_work_roster WHERE company_id=%s AND work_date=%s"""
        params = [actor.company_id, work_date]
        if after is not None:
            query += " AND employee_id>%s"
            params.append(after)
        query += " ORDER BY employee_id LIMIT %s"
        params.append(limit+1)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()
        page = rows[:limit]
        return {
            "rows": [{"employee_id": str(row[0]), "scheduled_to_work": row[1],
                      "recorded_by": str(row[2]), "recorded_at": row[3].isoformat()}
                     for row in page],
            "next_after": str(page[-1][0]) if len(rows)>limit else None,
        }
