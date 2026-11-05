"""Phase 52: explicitly invoked, read-only staging LoanHub acceptance probe.

No application route, credential provisioning, revocation mutation or CLI.
The caller supplies a trusted LoanHub public key and an approved test-borrower
token using a privileged staging runtime. Never expose token or loan values.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from .loanhub_remote_borrower_context import LoanHubRemoteBorrowerContext
from .loanhub_identity_verifier import LoanHubIdentityVerifier
from .loanhub_adapter import LoanHubBorrowerReadAdapter, LoanHubReadError
from .loanhub_grant_broker import LoanHubBorrowerGrantBroker
from .borrower_credential_gate import GuardedBorrowerTokenSource


class ProbeOutcome(str, Enum):
    VERIFIED_READ_ONLY = "verified_read_only"
    AUTHORIZATION_DENIED = "authorization_denied"
    LOAN_READ_UNAVAILABLE = "loan_read_unavailable"
    INVALID_STAGING_SCOPE = "invalid_staging_scope"


@dataclass(frozen=True)
class ProbeResult:
    outcome: ProbeOutcome
    # Intentionally contains no IDs, tokens, account details or balances.
    customer_access_enabled: bool = False
    payments_enabled: bool = False


def _uuid(value: str) -> str | None:
    try:
        canonical = str(UUID(value))
        return canonical if canonical == value else None
    except (TypeError, ValueError, AttributeError):
        return None


async def probe_approved_staging_borrower(
    *,
    loanhub_origin: str,
    approved_origin: str,
    company_id: str,
    borrower_id: str,
    borrower_access_token: str,
    trusted_public_key: object,
    approved_staging: bool,
    client: httpx.Client | None = None,
    async_client: httpx.AsyncClient | None = None,
) -> ProbeResult:
    """Only executes if an operator explicitly supplies trusted staging inputs.

    First verifies a signed access token and current /auth/me and
    /auth/borrower-context, then reads /loans/ through existing guarded
    adapters. Never mutates live state or enables a Batlokoa endpoint.
    """
    try:
        url = urlsplit(loanhub_origin)
        if (approved_staging is not True
                or not isinstance(approved_origin, str)
                or approved_origin != loanhub_origin
                or url.scheme != "https" or not url.hostname
                or url.username or url.password or url.query or url.fragment
                or url.path not in ("", "/")
                or not _uuid(company_id) or not _uuid(borrower_id)
                or trusted_public_key is None):
            return ProbeResult(ProbeOutcome.INVALID_STAGING_SCOPE)

        context = LoanHubRemoteBorrowerContext(
            base_url=loanhub_origin, client=client
        )
        verifier = LoanHubIdentityVerifier(
            base_url=loanhub_origin,
            public_key=trusted_public_key,
            resolve_remote_borrower_context=context,
            client=client,
        )
        # The bound supplier cannot switch to a different borrower or tenant.
        broker = LoanHubBorrowerGrantBroker(
            token_for=lambda t, b: (
                borrower_access_token
                if t == company_id and b == borrower_id else None
            ),
            verify_token_for=verifier,
        )
        grant = GuardedBorrowerTokenSource(broker)
        if grant(company_id, borrower_id) is None:
            return ProbeResult(ProbeOutcome.AUTHORIZATION_DENIED)

        loans = LoanHubBorrowerReadAdapter(
            base_url=loanhub_origin,
            borrower_token_for=grant,
            client=async_client,
        )
        # Avoid exposing loan details or counts in the result; actual loan
        # rows are still parsed and checked against both UUID boundaries.
        await loans.list_customer_loans(
            tenant_id=company_id, customer_id=borrower_id
        )
        return ProbeResult(ProbeOutcome.VERIFIED_READ_ONLY)
    except LoanHubReadError:
        return ProbeResult(ProbeOutcome.LOAN_READ_UNAVAILABLE)
    except Exception:
        # Staging-only diagnostic: never surface JWT, PII or transport errors.
        return ProbeResult(ProbeOutcome.LOAN_READ_UNAVAILABLE)
