"""Two-party verified account-link contract for Batlokoa customers.

This is an internal service layer only. It intentionally has no public API,
database implementation, OAuth login, or token exchange.

A link requires two independently verified identities, documented consent,
the same immutable central subject, an approved Batlokoa tenant membership,
and a transactional unique mapping persisted by a trusted store.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from .identity import CustomerContext, VerifiedClaims


class LinkDenied(Exception):
    """The requested link cannot be established."""


class LinkConflict(Exception):
    """Another identity already owns the requested account mapping."""


class LinkUnavailable(Exception):
    """The linking process is not safely configured or available."""


@dataclass(frozen=True, slots=True)
class LoanHubBorrowerProof:
    """Obtained from LoanHub after verifying an actual borrower-role session.

    DO NOT construct this from user-entered IDs, client JWT claims, or email.
    The proof issuer's integration must check the authenticated LoanHub user
    and borrower_profile relationship on the server.
    """
    borrower_id: UUID
    central_auth_subject: str
    role: str
    authenticated_at: datetime
    proof_id: str


@dataclass(frozen=True, slots=True)
class LinkConsent:
    subject: str
    tenant_id: UUID
    borrower_id: UUID
    acknowledged_at: datetime
    consent_reference: str


class TenantBorrowerVerifier(Protocol):
    async def is_active_tenant_borrower(
        self, *, tenant_id: UUID, borrower_id: UUID
    ) -> bool: ...


class AtomicLinkStore(Protocol):
    async def bind_once(
        self, *, issuer: str, subject: str, tenant_id: UUID,
        borrower_id: UUID, consent_reference: str, proof_id: str
    ) -> CustomerContext:
        """Uniquely claim BOTH subject and borrower in one transaction.

        Must guarantee atomic uniqueness of (issuer,subject,tenant) and
        (tenant,borrower_id), reject proof replay, and prevent remapping.
        """
        ...


@dataclass(frozen=True, slots=True)
class AccountLinkService:
    tenant_id: UUID
    issuer: str
    verifier: TenantBorrowerVerifier
    store: AtomicLinkStore
    max_proof_age_seconds: int = 300

    async def link(
        self, *, claims: VerifiedClaims, borrower: LoanHubBorrowerProof,
        consent: LinkConsent, now: datetime | None = None,
    ) -> CustomerContext:
        """Bind only after both identities and tenant are independently proven."""
        clock = now or datetime.now(timezone.utc)
        if clock.tzinfo is None:
            raise LinkDenied("Timezone-aware time is required")
        if not self.issuer.startswith("https://") or claims.iss != self.issuer:
            raise LinkDenied("Central issuer mismatch")
        if not 1 <= self.max_proof_age_seconds <= 600:
            raise LinkUnavailable("Proof expiry configuration is invalid")
        if (not claims.sub or borrower.role != "BORROWER"
                or borrower.central_auth_subject != claims.sub):
            raise LinkDenied("LoanHub borrower identity is not independently verified")
        if (not borrower.proof_id or len(borrower.proof_id) > 128
                or not consent.consent_reference or len(consent.consent_reference) > 128):
            raise LinkDenied("Missing link evidence")
        if (consent.subject != claims.sub or consent.tenant_id != self.tenant_id
                or consent.borrower_id != borrower.borrower_id):
            raise LinkDenied("Consent does not match verified account identities")
        if borrower.authenticated_at.tzinfo is None or consent.acknowledged_at.tzinfo is None:
            raise LinkDenied("Timestamp is not timezone-aware")
        age = (clock - borrower.authenticated_at).total_seconds()
        consent_age = (clock - consent.acknowledged_at).total_seconds()
        if (age < 0 or age > self.max_proof_age_seconds or
                consent_age < 0 or consent_age > self.max_proof_age_seconds):
            raise LinkDenied("Account verification or consent has expired")
        if not await self.verifier.is_active_tenant_borrower(
            tenant_id=self.tenant_id, borrower_id=borrower.borrower_id
        ):
            raise LinkDenied("Borrower does not belong to the active Batlokoa tenant")
        result = await self.store.bind_once(
            issuer=self.issuer,
            subject=claims.sub,
            tenant_id=self.tenant_id,
            borrower_id=borrower.borrower_id,
            consent_reference=consent.consent_reference,
            proof_id=borrower.proof_id,
        )
        if (result.tenant_id != str(self.tenant_id)
                or result.customer_id != str(borrower.borrower_id)
                or result.auth_subject != claims.sub):
            raise LinkUnavailable("Account-link store returned inconsistent identity")
        return result


class DisabledLinkStore:
    async def bind_once(
        self, *, issuer: str, subject: str, tenant_id: UUID,
        borrower_id: UUID, consent_reference: str, proof_id: str
    ) -> CustomerContext:
        raise LinkUnavailable("Account linking has not been provisioned")
