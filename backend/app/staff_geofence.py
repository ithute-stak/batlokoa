"""Pure geofence policy; not an authentication or tracking service."""
from dataclasses import dataclass
from enum import Enum
from math import asin, cos, isfinite, radians, sin, sqrt


class LocationState(str, Enum):
    INSIDE = "verified_inside"
    OUTSIDE = "verified_outside"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class Position:
    latitude: float
    longitude: float
    accuracy_m: float

    def valid(self) -> bool:
        return (
            all(isinstance(v, (int, float)) and not isinstance(v, bool)
                and isfinite(v) for v in
                (self.latitude, self.longitude, self.accuracy_m))
            and -90 <= self.latitude <= 90
            and -180 <= self.longitude <= 180
            and self.accuracy_m > 0
        )


def distance_m(a: Position, b: Position) -> float:
    if not a.valid() or not b.valid():
        raise ValueError("Invalid position")
    p, q = radians(a.latitude), radians(b.latitude)
    dlat = q - p
    dlon = radians(b.longitude - a.longitude)
    h = sin(dlat / 2)**2 + cos(p) * cos(q) * sin(dlon / 2)**2
    return 2 * 6371008.8 * asin(sqrt(min(1.0, max(0.0, h))))


def classify(branch: Position, sample: Position, *, radius_m: float = 10.0,
             fresh: bool = False) -> LocationState:
    """Freshness must be established by the calling trusted server boundary.

    Accuracy is a reported estimate, not proof of physical presence.
    Ambiguous readings never count as attendance or a confirmed exit.
    """
    if (not fresh or not branch.valid() or not sample.valid()
            or not isfinite(radius_m) or radius_m <= 0
            or branch.accuracy_m > radius_m
            or sample.accuracy_m > radius_m):
        return LocationState.UNVERIFIED
    distance = distance_m(branch, sample)
    uncertainty = branch.accuracy_m + sample.accuracy_m
    if distance + uncertainty <= radius_m:
        return LocationState.INSIDE
    if distance - uncertainty > radius_m:
        return LocationState.OUTSIDE
    return LocationState.UNVERIFIED
