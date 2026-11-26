"""Read-only owner inbox for confirmed attendance perimeter transitions.

This inbox does not mark external notification delivery as complete.
No raw coordinates or unrelated employee records are returned.
"""
from datetime import datetime
from uuid import UUID

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


    def read_access_events(self, identity, *, before_at=None, before_id=None, limit=50):
        """Newest-first access audit, independent of monitor sequence cursors.

        A fresh first-page read is required to discover newly committed events.
        No fake attendance session IDs or branch assignments are introduced.
        """
        if (not isinstance(identity, VerifiedStaffIdentity)
                or identity.active is not True
                or identity.role != "COMPANY_OWNER"
                or identity.company_wide_scope is not True):
            raise StaffAccessDenied("Verified company owner required")
        if (type(limit) is not int or not 1 <= limit <= 100
                or (before_at is None) != (before_id is None)):
            raise ValueError("Invalid access inbox pagination")
        if before_at is not None and (
                not isinstance(before_at, datetime) or before_at.utcoffset() is None
                or not isinstance(before_id, UUID)):
            raise ValueError("Invalid access inbox cursor")
        query = """SELECT event_id, employee_id, branch_id, event_type, observed_at
            FROM staff_attendance_access_events WHERE company_id=%s"""
        params = [identity.company_id]
        if before_at is not None:
            query += " AND (observed_at, event_id) < (%s, %s)"
            params.extend([before_at, before_id])
        query += " ORDER BY observed_at DESC, event_id DESC LIMIT %s"
        params.append(limit + 1)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()
        visible = rows[:limit]
        more = len(rows) > limit
        return {
            "events": [
                {"event_id": str(row[0]), "employee_id": str(row[1]),
                 "branch_id": str(row[2]) if row[2] is not None else None,
                 "event_type": row[3], "observed_at": row[4].isoformat()}
                for row in visible
            ],
            "next_before": {"observed_at": visible[-1][4].isoformat(),
                            "event_id": str(visible[-1][0])} if more else None,
            "has_more": more,
        }
