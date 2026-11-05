"""Phase 51: combine independent staging checks without enabling anything.

No credential bytes, HTTP calls, database access, or FastAPI state mutation.
Passing only means operator-supplied metadata passes local validation, not
that an actual borrower acceptance test has been completed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .staging_credential_provisioning import (
    StagingCredentialManifest,
    inspect_staging_credential_manifest,
)
from .staging_acceptance_evidence import (
    StagingAcceptanceEvidence,
    inspect_staging_acceptance,
)


@dataclass(frozen=True)
class StagingReadinessDecision:
    ready_for_manual_security_review: bool
    failures: tuple[str, ...]
    live_customer_access_enabled: bool = False
    payments_enabled: bool = False
    production_activation_authorized: bool = False


def inspect_staging_readiness(
    credentials: StagingCredentialManifest | None,
    acceptance: StagingAcceptanceEvidence | None,
    *,
    now: datetime | None = None,
) -> StagingReadinessDecision:
    """Require both gates, coherent identities and a common approval record."""
    credential_result = inspect_staging_credential_manifest(credentials, now=now)
    acceptance_result = inspect_staging_acceptance(acceptance, now=now)
    failures = [
        *(f"credential:{code}" for code in credential_result.failures),
        *(f"acceptance:{code}" for code in acceptance_result.failures),
    ]
    if isinstance(credentials, StagingCredentialManifest) and isinstance(
        acceptance, StagingAcceptanceEvidence
    ):
        if credentials.company_id != acceptance.company_id:
            failures.append("identity:company_mismatch")
        if credentials.approved_test_borrower_id != acceptance.approved_test_borrower_id:
            failures.append("identity:borrower_mismatch")
        if credentials.approval_reference != acceptance.security_approval_reference:
            failures.append("approval:reference_mismatch")
        if credentials.approval_expires_at != acceptance.security_approval_expires_at:
            failures.append("approval:expiry_mismatch")
        if credentials.loanhub_origin == "":
            failures.append("origin:missing")
    return StagingReadinessDecision(
        ready_for_manual_security_review=(
            credential_result.ready_for_operator_acceptance
            and acceptance_result.evidence_complete
            and not failures
        ),
        failures=tuple(failures),
    )
