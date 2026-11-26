"""Provider-neutral attendance dispatch worker; never starts automatically.

Only an explicitly configured company queue and an approved idempotent
adapter may be supplied. Provider acceptance is not proof of human receipt.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from .staff_attendance_notification_queue import AttendanceDeliveryQueue, DeliveryClaim


class DispatchOutcome(Enum):
    ACCEPTED = "accepted"
    RETRY = "retry"
    RECIPIENT_UNAVAILABLE = "recipient_unavailable"
    REJECTED = "rejected"


class AttendanceNotificationProvider(Protocol):
    def send(self, claim: DeliveryClaim, *, idempotency_key: str) -> DispatchOutcome:
        """Resolve current authorized recipient, send within lease deadline.

        Must deduplicate retries by key, including ambiguous network failures.
        Must not expose credentials, coordinates or unrelated employee details.
        """
        ...


@dataclass(frozen=True)
class DispatchReport:
    enqueued: int
    accepted: int
    deferred: int
    rejected: int
    lease_lost: int


class AttendanceDispatchWorker:
    def __init__(self, queue: AttendanceDeliveryQueue,
                 provider: AttendanceNotificationProvider, *, enabled=False):
        if type(enabled) is not bool:
            raise ValueError("Explicit release flag required")
        self._queue = queue
        self._provider = provider
        self._enabled = enabled

    def run_once(self, *, limit=20):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid dispatch batch")
        if not self._enabled:
            return DispatchReport(0, 0, 0, 0, 0)
        enqueued = self._queue.enqueue(limit=limit)
        accepted = deferred = rejected = lease_lost = 0
        for _ in range(limit):
            claim = self._queue.claim()
            if claim is None:
                break
            try:
                outcome = self._provider.send(
                    claim, idempotency_key=claim.idempotency_key)
            except Exception:
                # Provider exceptions may contain credentials or personal data.
                # Do not persist exception messages or infer delivery success.
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
        return DispatchReport(enqueued, accepted, deferred, rejected, lease_lost)
