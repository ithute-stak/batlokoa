"""Branch location registration policy, not yet wired to HTTP or storage.

All identity, directory, freshness and server time inputs must be supplied
by a trusted server adapter, never constructed from a browser request.
Browser geolocation alone cannot prove physical presence.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from .staff_authorization import VerifiedStaffIdentity, StaffAccessDenied
from .staff_geofence import Position

RADIUS_M = 10.0
MAX_SETUP_ACCURACY_M = 5.0


@dataclass(frozen=True)
class ActiveBranch:
    company_id: UUID
    branch_id: UUID
    active: bool


@dataclass(frozen=True)
class BranchLocation:
    company_id: UUID
    branch_id: UUID
    position: Position
    radius_m: float
    registered_by: UUID
    registered_at: datetime


def register_branch_location(
    identity: VerifiedStaffIdentity | None,
    branch: ActiveBranch,
    position: Position,
    *,
    fresh: bool = False,
    server_now: datetime,
) -> BranchLocation:
    """Produce a candidate for transactional persistence and audit.

    The owner-only initial policy deliberately excludes ordinary staff and
    administrators until delegated location-management rights are approved.
    The adapter must use strict verified-owner authentication, not the
    read-only pilot's unverified-owner exception.
    """
    if (not isinstance(identity, VerifiedStaffIdentity)
            or identity.active is not True
            or identity.role != "COMPANY_OWNER"
            or identity.company_wide_scope is not True
            or not isinstance(branch, ActiveBranch)
            or branch.active is not True
            or not isinstance(branch.company_id, UUID)
            or not isinstance(branch.branch_id, UUID)
            or identity.company_id != branch.company_id):
        raise StaffAccessDenied("Verified company owner and active branch required")
    if (fresh is not True or not isinstance(position, Position)
            or not position.valid()
            or position.accuracy_m > MAX_SETUP_ACCURACY_M):
        raise ValueError("Fresh high-accuracy location required")
    if (not isinstance(server_now, datetime) or server_now.tzinfo is None
            or server_now.utcoffset() is None):
        raise ValueError("Timezone-aware server timestamp required")
    return BranchLocation(
        company_id=branch.company_id, branch_id=branch.branch_id,
        position=position, radius_m=RADIUS_M,
        registered_by=identity.user_id,
        registered_at=server_now.astimezone(timezone.utc),
    )
