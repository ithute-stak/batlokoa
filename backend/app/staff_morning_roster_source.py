"""Company-scoped roster source for morning scheduling and dispatch.

The injected directory must authenticate a service identity and return a complete
fresh snapshot of verified LoanHub memberships. No owner browser token is used.
"""
from datetime import datetime, time
from typing import Protocol
from uuid import UUID

from .staff_authorization import VerifiedStaffIdentity
from .staff_morning_reminder import LESOTHO, ReminderCandidate
from .staff_morning_reminder_queue import MorningReminderClaim


class VerifiedEmployeeDirectory(Protocol):
    def employees(self, *, company_id, limit):
        """Return complete verified membership list or raise on uncertainty."""
        ...


class DatabaseMorningRosterSource:
    def __init__(self, connect, directory: VerifiedEmployeeDirectory, *, company_id):
        if not isinstance(company_id, UUID):
            raise ValueError("Explicit company required")
        self._connect = connect
        self._directory = directory
        self._company = company_id

    def _members(self):
        rows = self._directory.employees(company_id=self._company, limit=100)
        if not isinstance(rows, (list, tuple)) or len(rows) > 100:
            raise ValueError("Incomplete directory")
        members = {}
        for row in rows:
            if (not isinstance(row, VerifiedStaffIdentity)
                    or row.company_id != self._company
                    or row.user_id in members
                    or type(row.active) is not bool):
                raise ValueError("Unverified membership")
            members[row.user_id] = row
        return members

    @staticmethod
    def _active(member):
        return member is not None and member.active is True and member.role in {
            "COMPANY_OWNER", "COMPANY_ADMIN", "BRANCH_MANAGER",
            "LOAN_OFFICER", "CREDIT_ANALYST"}

    def _scheduled(self, work_date, employee_id=None, *, limit=100):
        start = datetime.combine(work_date, time.min, tzinfo=LESOTHO)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT r.employee_id, r.scheduled_to_work,
                        EXISTS (SELECT 1 FROM staff_attendance_sessions a
                          WHERE a.company_id=r.company_id AND a.employee_id=r.employee_id
                            AND (a.clocked_out_at IS NULL OR a.clocked_in_at >= %s))
                    FROM staff_morning_work_roster r
                    WHERE r.company_id=%s AND r.work_date=%s
                      AND (%s::uuid IS NULL OR r.employee_id=%s::uuid)
                    ORDER BY r.employee_id LIMIT %s""",
                    (start, self._company, work_date, employee_id, employee_id, limit+1))
                rows = cur.fetchall()
        if len(rows) > limit:
            raise ValueError("Roster exceeds bounded batch")
        return rows

    def candidates(self, *, company_id, work_date, limit):
        if company_id != self._company or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid roster scope or batch")
        members = self._members()
        return [ReminderCandidate(self._company, employee, work_date,
                    self._active(members.get(employee)), scheduled, clocked)
                for employee, scheduled, clocked in self._scheduled(work_date, limit=limit)]

    def refresh(self, claim):
        if not isinstance(claim, MorningReminderClaim) or claim.company_id != self._company:
            raise ValueError("Claim outside company scope")
        members = self._members()
        rows = self._scheduled(claim.work_date, claim.employee_id, limit=1)
        if not rows:
            # No explicit schedule: never deliver.
            return None
        employee, scheduled, clocked = rows[0]
        if employee != claim.employee_id:
            raise ValueError("Unexpected roster identity")
        return ReminderCandidate(self._company, employee, claim.work_date,
                    self._active(members.get(employee)), scheduled, clocked)
