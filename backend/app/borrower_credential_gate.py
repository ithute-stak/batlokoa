"""Fail-closed contract for backend-verified LoanHub borrower credentials.

LoanHub checks the authenticated user's DB role, active status, borrower profile
and local session revocation when serving GET /api/v1/loans/. The gateway must
not assume a token's unverified role claim provides this authorization.

The broker implementing this contract is deliberately absent. It must obtain
and verify LoanHub borrower identity and session state server-to-server, never
from Flutter, browser headers or JWT payloads decoded without verification.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import UUID


@dataclass(frozen=True)
class VerifiedBorrowerGrant:
    """Short-lived broker assertion; not itself proof of LoanHub authorization.

    Fields must be populated only after the trusted broker verifies LoanHub's
    effective DB-backed borrower role, linked borrower ID, active account and
    non-revoked session. The broker must recheck revocation on EVERY request.
    """

    token: str
    tenant_id: str
    borrower_id: str
    role: str
    expires_at: datetime
    checked_at: datetime
    identity_verified: bool
    session_active: bool


class GuardedBorrowerTokenSource:
    """Callable adapter for LoanHubBorrowerReadAdapter's backend-only supplier.

    Rejects stale, mismatched, expired, admin and revoked grants. The backend
    broker must itself verify signature, user identity and session revocation;
    these checks do not replace LoanHub's own authorization.
    """

    def __init__(
        self,
        broker: Callable[[str, str], VerifiedBorrowerGrant | None],
        *,
        max_check_age: timedelta = timedelta(seconds=15),
    ) -> None:
        if max_check_age <= timedelta(0) or max_check_age > timedelta(seconds=30):
            raise ValueError("Borrower-grant verification age must be short")
        self._broker = broker
        self._max_check_age = max_check_age

    def __call__(self, tenant_id: str, borrower_id: str) -> str | None:
        try:
            tenant = str(UUID(tenant_id))
            borrower = str(UUID(borrower_id))
        except (TypeError, ValueError):
            return None

        # Do not cache grants: the broker must recheck effective identity,
        # revocation and account link on each incoming customer request.
        grant = self._broker(tenant, borrower)
        if not isinstance(grant, VerifiedBorrowerGrant):
            return None
        if (grant.tenant_id != tenant or grant.borrower_id != borrower or
                grant.role != "borrower" or not grant.identity_verified or
                not grant.session_active or
                not isinstance(grant.token, str) or
                not 1 <= len(grant.token) <= 8192 or
                any(char.isspace() for char in grant.token)):
            return None

        if (not isinstance(grant.expires_at, datetime) or
                not isinstance(grant.checked_at, datetime) or
                grant.expires_at.tzinfo is None or
                grant.checked_at.tzinfo is None):
            return None
        now = datetime.now(timezone.utc)
        checked = grant.checked_at.astimezone(timezone.utc)
        expiry = grant.expires_at.astimezone(timezone.utc)
        if (checked > now or now - checked > self._max_check_age or
                expiry <= now + timedelta(seconds=1)):
            return None
        return grant.token
