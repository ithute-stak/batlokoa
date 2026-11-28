from datetime import datetime, timedelta, timezone

import pytest

from backend.app.staff_attendance_monitor import MonitorAlert, MonitorState, observe
from backend.app.staff_geofence import LocationState

START = datetime(2026, 11, 26, 5, tzinfo=timezone.utc)
INSIDE = LocationState.INSIDE
OUTSIDE = LocationState.OUTSIDE
UNKNOWN = LocationState.UNVERIFIED


def step(state, reading, seconds):
    return observe(state, reading, server_now=START + timedelta(seconds=seconds))


@pytest.mark.parametrize("seconds", [15, 30, 120])
def test_exit_requires_confirmation(seconds):
    state, alert = step(MonitorState(), OUTSIDE, 0)
    assert alert is None
    assert state.last_confirmed is INSIDE
    state, alert = step(state, OUTSIDE, seconds)
    assert alert is MonitorAlert.EXIT
    assert state.last_confirmed is OUTSIDE
    state, alert = step(state, OUTSIDE, seconds + 30)
    assert alert is None


def test_rapid_samples_do_not_confirm_exit():
    state, _ = step(MonitorState(), OUTSIDE, 0)
    for seconds in [1, 2, 14]:
        state, alert = step(state, OUTSIDE, seconds)
        assert alert is None
        assert state.last_confirmed is INSIDE
    state, alert = step(state, OUTSIDE, 15)
    assert alert is MonitorAlert.EXIT


def test_expired_candidate_restarts_confirmation():
    state, _ = step(MonitorState(), OUTSIDE, 0)
    state, alert = step(state, OUTSIDE, 121)
    assert alert is None
    assert state.candidate_since == START + timedelta(seconds=121)
    state, alert = step(state, OUTSIDE, 136)
    assert alert is MonitorAlert.EXIT


@pytest.mark.parametrize("interruption", [UNKNOWN, INSIDE])
def test_ambiguous_or_inside_reading_resets_pending_exit(interruption):
    state, _ = step(MonitorState(), OUTSIDE, 0)
    state, alert = step(state, interruption, 10)
    assert alert is None and state.candidate is None
    state, alert = step(state, OUTSIDE, 20)
    assert alert is None
    state, alert = step(state, OUTSIDE, 35)
    assert alert is MonitorAlert.EXIT


def test_return_requires_confirmation_and_does_not_repeat():
    state, _ = step(MonitorState(), OUTSIDE, 0)
    state, _ = step(state, OUTSIDE, 15)
    state, alert = step(state, UNKNOWN, 30)
    assert alert is None and state.last_confirmed is OUTSIDE
    state, alert = step(state, INSIDE, 45)
    assert alert is None and state.last_confirmed is OUTSIDE
    state, alert = step(state, INSIDE, 60)
    assert alert is MonitorAlert.RETURN
    state, alert = step(state, INSIDE, 75)
    assert alert is None and state.last_confirmed is INSIDE


@pytest.mark.parametrize("seconds", [0, -1])
def test_duplicate_and_backward_observation_times_rejected(seconds):
    state, _ = step(MonitorState(), OUTSIDE, 0)
    with pytest.raises(ValueError, match="time must advance"):
        step(state, OUTSIDE, seconds)


def test_naive_server_time_rejected():
    with pytest.raises(ValueError, match="Timezone-aware"):
        observe(MonitorState(), OUTSIDE, server_now=START.replace(tzinfo=None))
