from datetime import datetime, timedelta, timezone

import pytest

from app.staff_attendance_reporting_policy import classify_attendance


START = datetime(2026, 11, 28, 6, tzinfo=timezone.utc)
END = START + timedelta(hours=9)


def classify(**changes):
    values = dict(scheduled_to_work=True, shift_start=START, shift_end=END,
                  first_clock_in=None, as_of=END, records_complete=True,
                  grace_minutes=5)
    values.update(changes)
    return classify_attendance(**values)


@pytest.mark.parametrize("minutes,expected", [(-15, "on_time"), (0, "on_time"),
                                               (5, "on_time"), (6, "late")])
def test_grace_boundary(minutes, expected):
    assert classify(first_clock_in=START + timedelta(minutes=minutes)) == expected


def test_missing_clock_in_is_not_proof_of_absence():
    assert classify() == "no_recorded_clock_in"
    assert classify(as_of=START) == "pending_clock_in"
    assert classify(as_of=START - timedelta(seconds=1)) == "not_started"


def test_unknown_inputs():
    assert classify(records_complete=False) == "unknown"
    assert classify(scheduled_to_work=None) == "unknown"
    assert classify(shift_start=None) == "unknown"
    assert classify(scheduled_to_work=False) == "not_scheduled"


@pytest.mark.parametrize("changes", [
    {"grace_minutes": -1}, {"grace_minutes": 121},
    {"shift_end": START}, {"first_clock_in": END},
    {"first_clock_in": START, "as_of": START - timedelta(seconds=1)},
    {"shift_start": START.replace(tzinfo=None)},
])
def test_invalid_inputs(changes):
    with pytest.raises(ValueError):
        classify(**changes)
