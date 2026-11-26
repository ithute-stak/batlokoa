"""Morning reminder dispatch regression tests; synthetic recipients only."""
from dataclasses import replace
from datetime import date
from uuid import uuid4

import pytest

from backend.app.staff_morning_reminder import ReminderCandidate
from backend.app.staff_morning_reminder_queue import MorningReminderClaim
from backend.app.staff_morning_reminder_worker import MorningReminderWorker
from backend.app.staff_attendance_dispatch_worker import DispatchOutcome


@pytest.fixture
def scenario():
    claim = MorningReminderClaim(uuid4(), uuid4(), date(2026, 11, 26), uuid4(), 1)
    candidate = ReminderCandidate(claim.company_id, claim.employee_id,
                                  claim.work_date, True, True, False)
    return claim, candidate


class Queue:
    def __init__(self, claim, ready=True, fenced=True):
        self.pending = claim
        self.is_ready = ready
        self.fenced = fenced
        self.calls = []

    def claim(self):
        self.calls.append("claim")
        claim, self.pending = self.pending, None
        return claim

    def ready(self, claim, candidate):
        self.calls.append("ready")
        return self.is_ready

    def acknowledge(self, claim):
        self.calls.append("ack")
        return self.fenced

    def fail(self, claim, *, code, permanent):
        self.calls.append((code, permanent))
        return self.fenced


class Roster:
    def __init__(self, candidate):
        self.candidate = candidate
        self.calls = 0

    def refresh(self, claim):
        self.calls += 1
        if isinstance(self.candidate, Exception):
            raise self.candidate
        return self.candidate


class Provider:
    def __init__(self, outcome=DispatchOutcome.ACCEPTED):
        self.outcome = outcome
        self.calls = []

    def send(self, claim, *, idempotency_key):
        self.calls.append((claim, idempotency_key))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def test_disabled_worker_does_not_access_dependencies(scenario):
    claim, candidate = scenario
    queue, roster, provider = Queue(claim), Roster(candidate), Provider()
    report = MorningReminderWorker(queue, roster, provider).run_once()
    assert not queue.calls and not roster.calls and not provider.calls
    assert report.accepted == report.deferred == report.rejected == report.lease_lost == 0


@pytest.mark.parametrize("change", ["missing", "error", "company", "employee",
                                    "date", "unknown_active", "unknown_schedule",
                                    "unknown_attendance"])
def test_unverified_roster_never_sends(scenario, change):
    claim, candidate = scenario
    alternatives = {
        "missing": None,
        "error": RuntimeError("synthetic roster outage"),
        "company": replace(candidate, company_id=uuid4()),
        "employee": replace(candidate, employee_id=uuid4()),
        "date": replace(candidate, work_date=date(2026, 11, 25)),
        "unknown_active": replace(candidate, active=None),
        "unknown_schedule": replace(candidate, scheduled_to_work=None),
        "unknown_attendance": replace(candidate, already_clocked_in=None),
    }
    queue, provider = Queue(claim), Provider()
    report = MorningReminderWorker(queue, Roster(alternatives[change]),
                                   provider, enabled=True).run_once()
    assert not provider.calls
    assert "ready" not in queue.calls
    assert ("eligibility_unverified", False) in queue.calls
    assert report.deferred == 1 and report.accepted == 0


def test_database_recheck_blocks_delivery(scenario):
    claim, candidate = scenario
    queue, provider = Queue(claim, ready=False), Provider()
    report = MorningReminderWorker(queue, Roster(candidate), provider,
                                   enabled=True).run_once()
    assert not provider.calls
    assert ("no_longer_eligible", True) in queue.calls
    assert report.rejected == 1


@pytest.mark.parametrize("outcome,expected,code", [
    (DispatchOutcome.ACCEPTED, (1, 0, 0), None),
    (DispatchOutcome.RETRY, (0, 1, 0), ("provider_unavailable", False)),
    (DispatchOutcome.RECIPIENT_UNAVAILABLE, (0, 1, 0), ("recipient_unavailable", False)),
    (DispatchOutcome.REJECTED, (0, 0, 1), ("provider_rejected", True)),
    (RuntimeError("synthetic provider outage"), (0, 1, 0), ("provider_unavailable", False)),
])
def test_dispatch_outcomes(scenario, outcome, expected, code):
    claim, candidate = scenario
    queue, provider = Queue(claim), Provider(outcome)
    report = MorningReminderWorker(queue, Roster(candidate), provider,
                                   enabled=True).run_once(limit=1)
    assert provider.calls == [(claim, claim.idempotency_key)]
    assert (report.accepted, report.deferred, report.rejected) == expected
    assert queue.calls == ["claim", "ready", code if code else "ack"]


@pytest.mark.parametrize("outcome", [DispatchOutcome.ACCEPTED, DispatchOutcome.RETRY])
def test_stale_lease_not_counted_as_success(scenario, outcome):
    claim, candidate = scenario
    report = MorningReminderWorker(Queue(claim, fenced=False), Roster(candidate),
                                   Provider(outcome), enabled=True).run_once()
    assert report.lease_lost == 1
    assert report.accepted == report.deferred == report.rejected == 0


@pytest.mark.parametrize("limit", [0, 101, True, 1.5])
def test_invalid_batch_rejected(scenario, limit):
    claim, candidate = scenario
    queue = Queue(claim)
    with pytest.raises(ValueError):
        MorningReminderWorker(queue, Roster(candidate), Provider(),
                              enabled=True).run_once(limit=limit)
    assert not queue.calls
