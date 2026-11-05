"""Phase 50: acceptance metadata does not initiate customer access."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.staging_acceptance_evidence import (
    AcceptanceObservation,
    StagingAcceptanceEvidence,
    REQUIRED_CASES,
    inspect_staging_acceptance,
)


@pytest.fixture
def evidence():
    now = datetime.now(timezone.utc)
    return StagingAcceptanceEvidence(
        company_id="d921126e-e1a7-482e-ad1b-6e99b1682e19",
        approved_test_borrower_id="cb6700f8-1808-46ca-bfc2-f030ad0e2d7c",
        security_approval_reference="SEC-APPROVAL-50",
        security_approval_expires_at=now + timedelta(days=1),
        reviewed_by="security-reviewer-02",
        reviewed_at=now,
        observations=tuple(
            AcceptanceObservation(case, True, now, f"staging-evidence/{case}")
            for case in sorted(REQUIRED_CASES)
        ),
    )


def test_complete_synthetic_metadata_never_activates(evidence):
    decision = inspect_staging_acceptance(evidence)
    assert decision.evidence_complete
    assert not decision.production_activation_authorized
    assert not decision.payments_enabled


@pytest.mark.parametrize("field,value,reason", [
    ("environment", "production", "staging_only"),
    ("live_customer_access_enabled", True, "live_access_not_disabled"),
    ("payments_enabled", True, "payments_not_disabled"),
    ("approved_test_borrower_id", "invalid", "approved_identity_invalid"),
    ("security_approval_expires_at", datetime(2020, 1, 1, tzinfo=timezone.utc), "approval_expired"),
    ("reviewed_by", "", "independent_review_missing"),
])
def test_manifest_denials(evidence, field, value, reason):
    result = inspect_staging_acceptance(replace(evidence, **{field: value}))
    assert not result.evidence_complete
    assert reason in result.failures


def test_missing_case_fails(evidence):
    result = inspect_staging_acceptance(
        replace(evidence, observations=evidence.observations[:-1]))
    assert "required_cases_missing" in result.failures


def test_duplicate_case_fails(evidence):
    result = inspect_staging_acceptance(
        replace(evidence, observations=evidence.observations + (evidence.observations[0],)))
    assert "duplicate_case" in result.failures


def test_failed_case_fails(evidence):
    first = replace(evidence.observations[0], passed=False)
    result = inspect_staging_acceptance(
        replace(evidence, observations=(first,) + evidence.observations[1:]))
    assert "case_failed" in result.failures


def test_stale_case_fails(evidence):
    first = replace(evidence.observations[0], observed_at=datetime.now(timezone.utc) - timedelta(days=2))
    result = inspect_staging_acceptance(
        replace(evidence, observations=(first,) + evidence.observations[1:]))
    assert "case_stale" in result.failures


def test_extra_unknown_case_fails(evidence):
    extra = AcceptanceObservation("enable_payments", True, datetime.now(timezone.utc), "SEC-NOPE-1234")
    result = inspect_staging_acceptance(
        replace(evidence, observations=evidence.observations + (extra,)))
    assert "unknown_case" in result.failures


def test_missing_evidence_fails():
    assert inspect_staging_acceptance(None).failures == ("acceptance_evidence_missing",)
