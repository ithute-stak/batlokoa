"""Backend-only borrower grant broker orchestration; disabled without trusted inputs.

The real LoanHub identity verifier and token vault are intentionally NOT
configured. LoanHub currently authorizes GET /api/v1/loans/ with the effective
database UserRole.BORROWER, linked borrower_profile.id and active/revoked
session state. A JWT role claim alone is insufficient.

Only a server-controlled identity verifier may return BorrowerAccountEvidence.
Do not instantiate this broker using browser claims, decoded unsigned JWTs,
admin tokens, or self-reported credentials.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from uuid import UUID

from .borrower_credential_gate import VerifiedBorrowerGrant


@dataclass(frozen=True)
class BorrowerAccountEvidence:
    """Result of trusted LoanHub DB-backed authentication and authorization.

    The verifier must check token signature, expiry, actual LoanHub user,
    effective role, borrower profile, account active state, and session
    version/JTI revocation. The tenant/account relationship MUST also be
    confirmed by the trusted mapping service.
    """
    tenant_id: str
    borrower_id: str
    role: str
    account_active: bool
    session_active: bool
    verified_at: datetime


class LoanHubBorrowerGrantBroker:
    """Revalidates effective borrower identity before releasing each token.

    A private, server-side token vault retrieves a token for the exact tenant
    and borrower; a trusted verifier checks LoanHub authorization *for that
    token*. No token/identity cache is kept. Errors fail closed.
    """

    def __init__(
        self,
        *,
        token_for: Callable[[str, str], str | None],
        verify_token_for: Callable[[str, str, str], BorrowerAccountEvidence | None],
    ) -> None:
        self._token_for = token_for
        self._verify = verify_token_for

    def __call__(self, tenant_id: str, borrower_id: str) -> VerifiedBorrowerGrant | None:
        try:
            tenant = str(UUID(tenant_id))
            borrower = str(UUID(borrower_id))
        except (TypeError, ValueError, AttributeError):
            return None
        try:
            token = self._token_for(tenant, borrower)
            if (not isinstance(token, str) or not 1 <= len(token) <= 8192
                    or any(ch.isspace() for ch in token)):
                return None
            proof = self._verify(token, tenant, borrower)
            if not isinstance(proof, BorrowerAccountEvidence):
                return None
            if (proof.tenant_id != tenant or proof.borrower_id != borrower
                    or proof.role != "borrower" or not proof.account_active
                    or not proof.session_active or
                    not isinstance(proof.verified_at, datetime) or
                    proof.verified_at.tzinfo is None):
                return None
            checked_at = proof.verified_at.astimezone(timezone.utc)
            now = datetime.now(timezone.utc)
            # Proof must be fresh; reject clock skew or stale validation.
            if checked_at > now or (now - checked_at).total_seconds() > 10:
                return None
            # Token expiry must be verified by the trusted verifier before
            # it supplies evidence; do not parse client-provided expiry claims.
            expiry = self._verify_expiry(token, tenant, borrower)
            if expiry is None or expiry.tzinfo is None:
                return None
            expiry = expiry.astimezone(timezone.utc)
            if expiry <= now or expiry > now.replace(year=now.year + 1):
                return None
            return VerifiedBorrowerGrant(
                token=token, tenant_id=tenant, borrower_id=borrower,
                role="borrower", checked_at=checked_at, expires_at=expiry,
                identity_verified=True, session_active=True,
            )
        except Exception:
            # Secrets, HTTP and database errors are not customer-facing.
            return None

    def _verify_expiry(
        self, token: str, tenant_id: str, borrower_id: str
    ) -> datetime | None:
        """Overridden only by a trusted deployment subclass.

        Disabled by default: prevents an unsigned token-claims shortcut from
        accidentally becoming the production borrower credential broker.
        """
        return None
