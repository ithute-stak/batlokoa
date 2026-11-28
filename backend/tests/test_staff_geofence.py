import pytest

from backend.app.staff_geofence import LocationState, Position, classify, distance_m


BRANCH = Position(-29.31, 27.48, 1.0)


def sample(metres, accuracy=1.0):
    return Position(BRANCH.latitude + metres / 111195.08,
                    BRANCH.longitude, accuracy)


@pytest.mark.parametrize("metres, expected", [
    (0, LocationState.INSIDE),
    (7, LocationState.INSIDE),
    (9, LocationState.UNVERIFIED),
    (10, LocationState.UNVERIFIED),
    (11, LocationState.UNVERIFIED),
    (13, LocationState.OUTSIDE),
    (100, LocationState.OUTSIDE),
    (-13, LocationState.OUTSIDE),
])
def test_distance_policy(metres, expected):
    assert classify(BRANCH, sample(metres), fresh=True) == expected


def test_distance_units():
    assert distance_m(BRANCH, sample(10)) == pytest.approx(10, abs=0.01)


def test_stale_and_inaccurate():
    assert classify(BRANCH, sample(0)) == LocationState.UNVERIFIED
    assert classify(BRANCH, sample(0, 30), fresh=True) == LocationState.UNVERIFIED


@pytest.mark.parametrize("invalid", [
    Position(91, 0, 1), Position(0, 181, 1),
    Position(float("nan"), 0, 1), Position(0, 0, 0),
    Position(0, 0, -1), Position(0, 0, float("inf")),
])
def test_invalid_position(invalid):
    assert classify(BRANCH, invalid, fresh=True) == LocationState.UNVERIFIED
