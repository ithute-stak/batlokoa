"""Pure morning reminder eligibility policy; no scheduling or messaging side effects.

Roster inputs must be independently verified, current, and company-scoped.
Unknown working schedules or attendance status never imply absence.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

LESOTHO = timezone(timedelta(hours=2), "Africa/Maseru")


@dataclass(frozen=True)
class ReminderCandidate:
    company_id: UUID
    employee_id: UUID
    work_date: date
    active: bool
    scheduled_to_work: bool
    already_clocked_in: bool | None


def reminder_key(candidate, *, company_id, now):
    """Return a daily stable key during 07:00–07:14 local time, else None.

    No catch-up reminders outside the bounded morning window. Callers must
    enforce persistent uniqueness and recheck attendance before delivery.
    """
    if not isinstance(company_id, UUID):
        raise ValueError("Explicit company required")
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("Timezone-aware server time required")
    if not isinstance(candidate, ReminderCandidate):
        raise ValueError("Verified roster candidate required")
    local = now.astimezone(LESOTHO)
    if (candidate.company_id != company_id
            or not isinstance(candidate.employee_id, UUID)
            or candidate.work_date != local.date()
            or candidate.active is not True
            or candidate.scheduled_to_work is not True
            or candidate.already_clocked_in is not False
            or not time(7) <= local.time() < time(7, 15)):
        return None
    return f"batlokoa:morning:{company_id}:{candidate.employee_id}:{local.date().isoformat()}"
