"""Morning clock-in reminder policy regression tests."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from backend.app.staff_morning_reminder import ReminderCandidate, reminder_key


@pytest.fixture
def candidate():
    return ReminderCandidate(uuid4(), uuid4(), date(2026, 11, 26),
                             True, True, False)


def evaluate(candidate, hour=5, minute=0, second=0, **kwargs):
    return reminder_key(candidate,
        company_id=kwargs.get("company_id", candidate.company_id),
        now=datetime(2026, 11, 26, hour, minute, second, tzinfo=timezone.utc))


@pytest.mark.parametrize("hour,minute,second,eligible", [
    (4, 59, 59, False),
    (5, 0, 0, True),
    (5, 14, 59, True),
    (5, 15, 0, False),
    (6, 0, 0, False),
    (23, 0, 0, False),
])
def test_local_morning_window(candidate, hour, minute, second, eligible):
    assert (evaluate(candidate, hour, minute, second) is not None) == eligible


@pytest.mark.parametrize("changes", [
    {"active": False},
    {"active": None},
    {"scheduled_to_work": False},
    {"scheduled_to_work": None},
    {"already_clocked_in": True},
    {"already_clocked_in": None},
    {"work_date": date(2026, 11, 25)},
    {"work_date": date(2026, 11, 27)},
    {"employee_id": "not-a-uuid"},
])
def test_ineligible_or_unknown_roster(candidate, changes):
    assert evaluate(replace(candidate, **changes)) is None


def test_company_scope(candidate):
    assert evaluate(candidate, company_id=uuid4()) is None


def test_stable_daily_key(candidate):
    key = evaluate(candidate)
    assert key == (f"batlokoa:morning:{candidate.company_id}:"
                   f"{candidate.employee_id}:2026-11-26")
    assert key == evaluate(candidate, 5, 14, 59)
    assert key != evaluate(replace(candidate, employee_id=uuid4()))
    different_company = replace(candidate, company_id=uuid4())
    assert key != evaluate(different_company)
    tomorrow = replace(candidate, work_date=candidate.work_date+timedelta(days=1))
    tomorrow_key = reminder_key(tomorrow, company_id=tomorrow.company_id,
        now=datetime(2026, 11, 27, 5, tzinfo=timezone.utc))
    assert tomorrow_key is not None and tomorrow_key != key


def test_offset_independence(candidate):
    local_now = datetime(2026, 11, 26, 7, tzinfo=timezone(timedelta(hours=2)))
    assert reminder_key(candidate, company_id=candidate.company_id,
                        now=local_now) == evaluate(candidate)


def test_invalid_server_inputs(candidate):
    with pytest.raises(ValueError):
        reminder_key(candidate, company_id=candidate.company_id,
                     now=datetime(2026, 11, 26, 7))
    with pytest.raises(ValueError):
        evaluate(candidate, company_id=str(candidate.company_id))
    with pytest.raises(ValueError):
        reminder_key(None, company_id=candidate.company_id,
                     now=datetime(2026, 11, 26, 5, tzinfo=timezone.utc))
