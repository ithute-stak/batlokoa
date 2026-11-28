"""Provider-neutral dispatch regression tests; no external messages are sent."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from backend.app.staff_attendance_dispatch_worker import (
    AttendanceDispatchWorker, DispatchOutcome, DispatchReport,
)
from backend.app.staff_attendance_notification_queue import DeliveryClaim


class FakeQueue:
    def __init__(self):
        self.item = DeliveryClaim(1, uuid4(), uuid4(), uuid4(),
                                  "reported_outside_perimeter",
                                  datetime.now(timezone.utc), uuid4(), 1)
        self.enqueues = []
        self.claims = 0
        self.acks = []
        self.failures = []
        self.fenced = False

    def enqueue(self, *, limit):
        self.enqueues.append(limit)
        return 1

    def claim(self):
        self.claims += 1
        return self.item if self.claims == 1 else None

    def acknowledge(self, claim):
        self.acks.append(claim)
        return not self.fenced

    def fail(self, claim, *, code, permanent=False):
        self.failures.append((claim, code, permanent))
        return not self.fenced


class FakeProvider:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def send(self, claim, *, idempotency_key):
        self.calls.append((claim, idempotency_key))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def test_disabled_worker_has_no_queue_or_provider_side_effects():
    queue, provider = FakeQueue(), FakeProvider(DispatchOutcome.ACCEPTED)
    assert AttendanceDispatchWorker(queue, provider).run_once() == DispatchReport(0, 0, 0, 0, 0)
    assert queue.enqueues == provider.calls == []
    assert queue.claims == 0


def test_acceptance_uses_stable_key_and_acknowledges_only_once():
    queue, provider = FakeQueue(), FakeProvider(DispatchOutcome.ACCEPTED)
    report = AttendanceDispatchWorker(queue, provider, enabled=True).run_once(limit=1)
    assert report == DispatchReport(1, 1, 0, 0, 0)
    assert provider.calls == [(queue.item, queue.item.idempotency_key)]
    assert queue.acks == [queue.item]
    assert queue.claims == 1 and not queue.failures


@pytest.mark.parametrize("outcome,code,permanent", [
    (DispatchOutcome.RETRY, "provider_unavailable", False),
    (DispatchOutcome.RECIPIENT_UNAVAILABLE, "recipient_unavailable", False),
    (DispatchOutcome.REJECTED, "provider_rejected", True),
    (RuntimeError("synthetic sensitive provider error"), "provider_unavailable", False),
    (None, "provider_unavailable", False),
])
def test_failure_never_acknowledges_and_only_persists_safe_codes(outcome, code, permanent):
    queue, provider = FakeQueue(), FakeProvider(outcome)
    report = AttendanceDispatchWorker(queue, provider, enabled=True).run_once()
    assert queue.acks == []
    assert queue.failures == [(queue.item, code, permanent)]
    assert report == DispatchReport(1, 0, int(not permanent), int(permanent), 0)


@pytest.mark.parametrize("outcome", [DispatchOutcome.ACCEPTED, DispatchOutcome.RETRY])
def test_stale_lease_cannot_report_success_or_retry(outcome):
    queue, provider = FakeQueue(), FakeProvider(outcome)
    queue.fenced = True
    report = AttendanceDispatchWorker(queue, provider, enabled=True).run_once()
    assert report == DispatchReport(1, 0, 0, 0, 1)


@pytest.mark.parametrize("limit", [0, -1, 101, True, 1.5])
def test_invalid_batch_rejected_before_work(limit):
    queue, provider = FakeQueue(), FakeProvider(DispatchOutcome.ACCEPTED)
    with pytest.raises(ValueError):
        AttendanceDispatchWorker(queue, provider, enabled=True).run_once(limit=limit)
    assert queue.enqueues == provider.calls == []
