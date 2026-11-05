"""Phase 50: offline staging acceptance-evidence decision, never activation.

This gate evaluates redacted, independently verified observations. It does
not perform network calls, generate credentials, configure routes, or certify
that a real borrower test was performed merely because data was supplied.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

REQUIRED_CASES = frozenset({
    "approved_borrower_login",
    "same_company_read_only_loan_read",
    "cross_company_denied",
    "other_borrower_denied",
    "logout_revokes_access",
    "session_jti_revoked",
    "session_version_changed",
    "expired_token_denied",
    "upstream_outage_fails_closed",
    "payments_remain_disabled",
    "public_demo_remains_disabled",
})

@dataclass(frozen=True)
class AcceptanceObservation:
    case: str
    passed: bool
    observed_at: datetime
    evidence_reference: str

@dataclass(frozen=True)
class StagingAcceptanceEvidence:
    company_id: str
    approved_test_borrower_id: str
    security_approval_reference: str
    security_approval_expires_at: datetime
    reviewed_by: str
    reviewed_at: datetime
    observations: tuple[AcceptanceObservation, ...]
    environment: str = "staging"
    live_customer_access_enabled: bool = False
    payments_enabled: bool = False

@dataclass(frozen=True)
class AcceptanceDecision:
    evidence_complete: bool
    failures: tuple[str, ...]
    # Passing the checklist does not authorize or bootstrap production.
    production_activation_authorized: bool = False
    payments_enabled: bool = False


def _uuid(value: object) -> bool:
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except (TypeError, ValueError, AttributeError):
        return False


def _reference(value: object) -> bool:
    return (isinstance(value, str) and 8 <= len(value.strip()) <= 120
            and all(ch.isalnum() or ch in "-_.:/" for ch in value))


def _time(value: object, now: datetime) -> bool:
    return (isinstance(value, datetime) and value.tzinfo is not None
            and value.astimezone(timezone.utc) <= now)


def inspect_staging_acceptance(
    evidence: StagingAcceptanceEvidence | None,
    *,
    now: datetime | None = None,
    max_observation_age_seconds: int = 86400,
) -> AcceptanceDecision:
    if not isinstance(evidence, StagingAcceptanceEvidence):
        return AcceptanceDecision(False, ("acceptance_evidence_missing",))
    failures: list[str] = []
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return AcceptanceDecision(False, ("inspection_time_invalid",))
    current = current.astimezone(timezone.utc)
    if evidence.environment != "staging":
        failures.append("staging_only")
    if evidence.live_customer_access_enabled is not False:
        failures.append("live_access_not_disabled")
    if evidence.payments_enabled is not False:
        failures.append("payments_not_disabled")
    if not _uuid(evidence.company_id) or not _uuid(evidence.approved_test_borrower_id):
        failures.append("approved_identity_invalid")
    if not _reference(evidence.security_approval_reference):
        failures.append("approval_reference_invalid")
    expiry = evidence.security_approval_expires_at
    if (not isinstance(expiry, datetime) or expiry.tzinfo is None or
            expiry.astimezone(timezone.utc) <= current):
        failures.append("approval_expired")
    if not _reference(evidence.reviewed_by) or not _time(evidence.reviewed_at, current):
        failures.append("independent_review_missing")
    if not isinstance(max_observation_age_seconds, int) or not 1 <= max_observation_age_seconds <= 86400:
        return AcceptanceDecision(False, ("inspection_window_invalid",))
    observations = evidence.observations
    if not isinstance(observations, (tuple, list)):
        return AcceptanceDecision(False, ("observations_invalid",))
    seen: set[str] = set()
    for observation in observations:
        if not isinstance(observation, AcceptanceObservation):
            failures.append("observation_invalid")
            continue
        if observation.case not in REQUIRED_CASES:
            failures.append("unknown_case")
        if observation.case in seen:
            failures.append("duplicate_case")
        seen.add(observation.case)
        if observation.passed is not True:
            failures.append("case_failed")
        if not _reference(observation.evidence_reference):
            failures.append("case_reference_missing")
        if not _time(observation.observed_at, current):
            failures.append("case_time_invalid")
        elif (current - observation.observed_at.astimezone(timezone.utc)).total_seconds() > max_observation_age_seconds:
            failures.append("case_stale")
    if seen != REQUIRED_CASES:
        failures.append("required_cases_missing")
    return AcceptanceDecision(not failures, tuple(dict.fromkeys(failures)))
