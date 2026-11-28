"""Offline PostgreSQL adapter; requires reviewed runtime grants and bootstrap."""
from datetime import datetime, timezone

from .staff_authorization import VerifiedStaffIdentity, StaffAccessDenied
from .staff_branch_location import ActiveBranch, BranchLocation, register_branch_location
from .staff_geofence import Position


class BranchLocationStore:
    """Connection factory must return a dedicated psycopg connection.

    Identity and branch directory evidence must be freshly verified upstream.
    No raw browser identity or arbitrary SQL identifiers are accepted.
    """

    def __init__(self, connect):
        self._connect = connect

    def register(self, identity, branch, position, *, fresh=False):
        location = register_branch_location(
            identity, branch, position, fresh=fresh,
            server_now=datetime.now(timezone.utc),
        )
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO staff_branch_location_history
                       (company_id, branch_id, latitude, longitude, accuracy_m,
                        radius_m, registered_by)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       RETURNING revision_id, registered_at""",
                    (location.company_id, location.branch_id,
                     position.latitude, position.longitude, position.accuracy_m,
                     location.radius_m, location.registered_by),
                )
                revision, timestamp = cur.fetchone()
        return revision, timestamp

    def current(self, identity, branch):
        if (not isinstance(identity, VerifiedStaffIdentity)
                or identity.active is not True
                or not isinstance(branch, ActiveBranch)
                or branch.active is not True
                or identity.company_id != branch.company_id
                or identity.role not in {
                    "COMPANY_OWNER", "COMPANY_ADMIN", "BRANCH_MANAGER",
                    "LOAN_OFFICER", "CREDIT_ANALYST",
                }
                or not (
                    branch.branch_id in identity.branch_ids
                    or (identity.company_wide_scope is True and identity.role
                        in {"COMPANY_OWNER", "COMPANY_ADMIN"})
                )):
            raise StaffAccessDenied("Active assigned staff required")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT revision_id, latitude, longitude, accuracy_m,
                              radius_m, registered_by, registered_at
                       FROM staff_branch_location_history
                       WHERE company_id = %s AND branch_id = %s
                       ORDER BY revision_id DESC LIMIT 1""",
                    (identity.company_id, branch.branch_id),
                )
                row = cur.fetchone()
        if row is None:
            return None
        revision, lat, lon, accuracy, radius, actor, timestamp = row
        position = Position(lat, lon, accuracy)
        if not position.valid() or accuracy > 5 or radius != 10:
            raise ValueError("Invalid stored branch location")
        return revision, BranchLocation(
            identity.company_id, branch.branch_id, position,
            radius, actor, timestamp,
        )
