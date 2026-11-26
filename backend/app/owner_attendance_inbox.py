"""Read-only owner inbox for confirmed attendance perimeter transitions.

This inbox does not mark external notification delivery as complete.
No raw coordinates or unrelated employee records are returned.
"""
from .staff_authorization import VerifiedStaffIdentity, StaffAccessDenied


class OwnerAttendanceInbox:
    def __init__(self, connect):
        self._connect = connect

    def read(self, identity, *, after=0, limit=50):
        if (not isinstance(identity, VerifiedStaffIdentity)
                or identity.active is not True
                or identity.role != "COMPANY_OWNER"
                or identity.company_wide_scope is not True):
            raise StaffAccessDenied("Verified company owner required")
        if (type(after) is not int or not 0 <= after <= 9223372036854775807
                or type(limit) is not int or not 1 <= limit <= 100):
            raise ValueError("Invalid inbox pagination")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT alert_id, session_id, employee_id, branch_id,
                                      event_type, observed_at
                    FROM staff_attendance_monitor_outbox
                    WHERE company_id=%s AND alert_id>%s
                    ORDER BY alert_id ASC LIMIT %s""",
                    (identity.company_id, after, limit + 1))
                rows = cur.fetchall()
        visible = rows[:limit]
        return {
            "alerts": [
                {"alert_id": row[0], "session_id": row[1],
                 "employee_id": str(row[2]), "branch_id": str(row[3]),
                 "event_type": row[4], "observed_at": row[5].isoformat()}
                for row in visible
            ],
            "next_after": visible[-1][0] if visible else after,
            "has_more": len(rows) > limit,
        }
