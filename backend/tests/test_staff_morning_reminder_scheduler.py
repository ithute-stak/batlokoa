from datetime import date, datetime, timezone
from dataclasses import replace
from uuid import uuid4

import pytest

from backend.app.staff_morning_reminder import ReminderCandidate
from backend.app.staff_morning_reminder_scheduler import MorningReminderScheduler


COMPANY = uuid4()
DAY = date(2026, 11, 26)
NOW = datetime(2026, 11, 26, 5, 0, tzinfo=timezone.utc)


class Source:
    def __init__(self, candidates):
        self.rows = candidates
        self.calls = []

    def candidates(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.rows, Exception):
            raise self.rows
        return self.rows


class Queue:
    def __init__(self):
        self.calls = []
        self.keys = set()

    def enqueue(self, candidate):
        self.calls.append(candidate)
        key = (candidate.company_id, candidate.employee_id, candidate.work_date)
        if key in self.keys:
            return False
        self.keys.add(key)
        return True


def candidate(**kwargs):
    return replace(ReminderCandidate(COMPANY, uuid4(), DAY, True, True, False), **kwargs)


def scheduler(rows, *, now=NOW, enabled=True):
    queue, source = Queue(), Source(rows)
    service = MorningReminderScheduler(queue, source, company_id=COMPANY,
                                       enabled=enabled, clock=lambda: now)
    return service, queue, source


def test_disabled_scheduler_does_not_access_roster():
    service, queue, source = scheduler([candidate()], enabled=False)
    assert service.tick().enqueued == 0
    assert not source.calls and not queue.calls


@pytest.mark.parametrize("hour,minute", [(4, 59), (5, 15), (6, 0), (23, 59)])
def test_no_reminder_outside_local_window(hour, minute):
    service, queue, source = scheduler([candidate()], now=NOW.replace(hour=hour, minute=minute))
    assert service.tick().enqueued == 0
    assert not source.calls and not queue.calls


def test_only_explicitly_eligible_staff_and_daily_deduplication():
    eligible = candidate()
    service, queue, source = scheduler([
        eligible, candidate(active=False), candidate(scheduled_to_work=False),
        candidate(already_clocked_in=True), candidate(already_clocked_in=None),
    ])
    report = service.tick()
    assert (report.considered, report.enqueued, report.unavailable) == (5, 1, False)
    assert source.calls == [{"company_id": COMPANY, "work_date": DAY, "limit": 100}]
    assert queue.calls == [eligible]
    assert service.tick().enqueued == 0
    assert len(queue.keys) == 1


@pytest.mark.parametrize("invalid", [
    lambda row: replace(row, company_id=uuid4()),
    lambda row: replace(row, work_date=date(2026, 11, 25)),
    lambda row: replace(row, active=1),
    lambda row: replace(row, scheduled_to_work=None),
    lambda row: replace(row, already_clocked_in=0),
    lambda row: replace(row, employee_id="invalid"),
    lambda row: row,
])
def test_invalid_batch_never_partially_enqueues(invalid):
    first = candidate()
    service, queue, _ = scheduler([first, invalid(first)])
    assert service.tick().unavailable
    assert not queue.calls


def test_unavailable_directory_and_oversized_batch_fail_closed():
    for rows in (RuntimeError("unavailable"), [candidate(), candidate()], iter([candidate()])):
        service, queue, _ = scheduler(rows)
        assert service.tick(limit=1).unavailable
        assert not queue.calls


def test_last_minute_of_window_allowed():
    service, queue, _ = scheduler([candidate()], now=NOW.replace(minute=14, second=59))
    assert service.tick().enqueued == 1
    assert len(queue.calls) == 1


@pytest.mark.parametrize("limit", [0, 101, True, 1.5])
def test_invalid_limits_rejected(limit):
    service, queue, source = scheduler([])
    with pytest.raises(ValueError):
        service.tick(limit=limit)
    assert not queue.calls and not source.calls


def test_naive_clock_rejected():
    service, queue, source = scheduler([candidate()], now=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError):
        service.tick()
    assert not queue.calls and not source.calls
