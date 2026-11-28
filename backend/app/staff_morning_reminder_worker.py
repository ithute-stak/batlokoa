"""Opt-in morning reminder worker; no automatic scheduling or live provider.

The roster source must independently verify current employment and schedule.
The receiving provider must enforce the daily key, expiry and recipient scope.
"""
from typing import Protocol

from .staff_morning_reminder import ReminderCandidate
from .staff_morning_reminder_queue import MorningReminderClaim, MorningReminderQueue
from .staff_attendance_dispatch_worker import DispatchOutcome, DispatchReport


class MorningRosterSource(Protocol):
    def refresh(self, claim: MorningReminderClaim) -> ReminderCandidate | None:
        """Return a freshly verified candidate or None when unavailable."""
        ...


class MorningReminderProvider(Protocol):
    def send(self, claim: MorningReminderClaim, *, idempotency_key: str) -> DispatchOutcome:
        """Resolve employee recipient and enforce expiry and retry deduplication."""
        ...


class MorningReminderWorker:
    def __init__(self, queue: MorningReminderQueue, roster: MorningRosterSource,
                 provider: MorningReminderProvider, *, enabled=False):
        if type(enabled) is not bool:
            raise ValueError("Explicit release flag required")
        self._queue = queue
        self._roster = roster
        self._provider = provider
        self._enabled = enabled

    def run_once(self, *, limit=20):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid dispatch batch")
        if not self._enabled:
            return DispatchReport(0, 0, 0, 0, 0)
        accepted = deferred = rejected = lease_lost = 0
        for _ in range(limit):
            claim = self._queue.claim()
            if claim is None:
                break
            try:
                candidate = self._roster.refresh(claim)
                verified = (isinstance(candidate, ReminderCandidate)
                    and candidate.company_id == claim.company_id
                    and candidate.employee_id == claim.employee_id
                    and candidate.work_date == claim.work_date
                    and type(candidate.active) is bool
                    and type(candidate.scheduled_to_work) is bool
                    and type(candidate.already_clocked_in) is bool)
            except Exception:
                verified = False
            if not verified:
                code, permanent = "eligibility_unverified", False
            elif not self._queue.ready(claim, candidate):
                code, permanent = "no_longer_eligible", True
            else:
                try:
                    outcome = self._provider.send(claim, idempotency_key=claim.idempotency_key)
                except Exception:
                    outcome = DispatchOutcome.RETRY
                if outcome is DispatchOutcome.ACCEPTED:
                    if self._queue.acknowledge(claim):
                        accepted += 1
                    else:
                        lease_lost += 1
                    continue
                if outcome is DispatchOutcome.REJECTED:
                    code, permanent = "provider_rejected", True
                elif outcome is DispatchOutcome.RECIPIENT_UNAVAILABLE:
                    code, permanent = "recipient_unavailable", False
                else:
                    code, permanent = "provider_unavailable", False
            if not self._queue.fail(claim, code=code, permanent=permanent):
                lease_lost += 1
            elif permanent:
                rejected += 1
            else:
                deferred += 1
        return DispatchReport(0, accepted, deferred, rejected, lease_lost)
