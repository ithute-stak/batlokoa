"""Bounded, opt-in morning reminder scheduling orchestration.

An external trusted scheduler invokes tick periodically. No threads, live
provider, credentials, or implicit company discovery are created here.
"""
from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Protocol
from uuid import UUID

from .staff_morning_reminder import LESOTHO, ReminderCandidate, reminder_key


class MorningCandidateSource(Protocol):
    def candidates(self, *, company_id, work_date, limit):
        """Return a complete bounded sequence of freshly verified candidates.

        Raise if the directory or schedule cannot be verified completely.
        """
        ...


@dataclass(frozen=True)
class MorningScheduleReport:
    considered: int = 0
    enqueued: int = 0
    unavailable: bool = False


class MorningReminderScheduler:
    def __init__(self, queue, source: MorningCandidateSource, *, company_id,
                 enabled=False, clock=None):
        if not isinstance(company_id, UUID) or type(enabled) is not bool:
            raise ValueError("Explicit company and release flag required")
        self._queue = queue
        self._source = source
        self._company = company_id
        self._enabled = enabled
        self._clock = clock if clock is not None else lambda: datetime.now(timezone.utc)

    def tick(self, *, limit=100):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid candidate batch")
        if not self._enabled:
            return MorningScheduleReport()
        now = self._clock()
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise ValueError("Timezone-aware server clock required")
        local = now.astimezone(LESOTHO)
        if not time(7) <= local.time() < time(7, 15):
            return MorningScheduleReport()
        try:
            candidates = self._source.candidates(
                company_id=self._company, work_date=local.date(), limit=limit)
            if not isinstance(candidates, (list, tuple)) or len(candidates) > limit:
                raise ValueError("Incomplete or oversized roster")
            seen = set()
            eligible = []
            for item in candidates:
                if (not isinstance(item, ReminderCandidate)
                        or item.company_id != self._company
                        or item.work_date != local.date()
                        or not isinstance(item.employee_id, UUID)
                        or item.employee_id in seen
                        or type(item.active) is not bool
                        or type(item.scheduled_to_work) is not bool
                        or (item.already_clocked_in is not None
                            and type(item.already_clocked_in) is not bool)):
                    raise ValueError("Unverified roster candidate")
                seen.add(item.employee_id)
                if reminder_key(item, company_id=self._company, now=now) is not None:
                    eligible.append(item)
        except Exception:
            return MorningScheduleReport(unavailable=True)
        enqueued = 0
        for item in eligible:
            # The persistent queue independently checks database time and
            # actual attendance, and deduplicates concurrent ticks.
            if self._queue.enqueue(item):
                enqueued += 1
        return MorningScheduleReport(len(candidates), enqueued)
