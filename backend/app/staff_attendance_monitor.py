"""Pure active-session monitoring policy; no background collection or delivery.

Reported GPS is an estimate, not attestation. Persist state atomically per
attendance session and notify only on a confirmed state transition.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from .staff_geofence import LocationState


class MonitorAlert(str, Enum):
    EXIT = "reported_outside_perimeter"
    RETURN = "reported_inside_perimeter"


@dataclass(frozen=True)
class MonitorState:
    last_observed_at: datetime | None = None
    last_confirmed: LocationState = LocationState.INSIDE
    candidate_since: datetime | None = None
    candidate: LocationState | None = None


def observe(previous: MonitorState, reading: LocationState, *,
            server_now: datetime) -> tuple[MonitorState, MonitorAlert | None]:
    """Require two consistent observations 15–120 seconds apart.

    Missing or ambiguous readings reset the pending transition, not the last
    confirmed state. Repeated outside readings do not generate repeat alerts.
    The caller must verify identity, open session, branch and sample freshness.
    """
    if not isinstance(server_now, datetime) or server_now.utcoffset() is None:
        raise ValueError("Timezone-aware server time required")
    if not isinstance(previous, MonitorState) or not isinstance(reading, LocationState):
        raise ValueError("Invalid monitoring state")
    if previous.last_observed_at is not None and server_now <= previous.last_observed_at:
        raise ValueError("Observation time must advance")
    confirmed = previous.last_confirmed
    if reading is LocationState.UNVERIFIED or reading is confirmed:
        return MonitorState(server_now, confirmed), None
    since = previous.candidate_since
    if (previous.candidate is not reading or since is None
            or server_now - since > timedelta(seconds=120)):
        return MonitorState(server_now, confirmed, server_now, reading), None
    if server_now - since < timedelta(seconds=15):
        return MonitorState(server_now, confirmed, since, reading), None
    alert = MonitorAlert.EXIT if reading is LocationState.OUTSIDE else MonitorAlert.RETURN
    return MonitorState(server_now, reading), alert
