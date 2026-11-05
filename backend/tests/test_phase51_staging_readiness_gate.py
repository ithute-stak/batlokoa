"""Phase 51: synthetic metadata proves gates fail closed, never activates."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.staging_credential_provisioning import StagingCredentialManifest
from backend.app.staging_acceptance_evidence import (
    StagingAcceptanceEvidence, AcceptanceObservation, REQUIRED_CASES,
)
from backend.app.staging_readiness_gate import inspect_staging_readiness


@pytest.fixture
def records(tmp_path):
    token = tmp_path / "token"
    public = tmp_path / "public"
    token.write_text("SYNTHETIC_NOT_A_REAL_TOKEN")
    public.write_text("SYNTHETIC_NOT_A_REAL_KEY")
    token.chmod(0o600)
    public.chmod(0o600)
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(hours=2)
    company_id = "d921126e-e1a7-482e-ad1b-6e99b1682e19"
    borrower_id = "cb6700f8-1808-46ca-bfc2-f030ad0e2d7c"
    credentials = StagingCredentialManifest(
        company_id=company_id,
        loanhub_origin="https://loanhub-staging.example.invalid",
        borrower_token_path=str(token),
        loanhub_public_key_path=str(public),
        approved_test_borrower_id=borrower_id,
        approval_reference="APPROVAL-PHASE51",
        approval_expires_at=expiry,
    )
    acceptance = StagingAcceptanceEvidence(
        company_id=company_id,
        approved_test_borrower_id=borrower_id,
        security_approval_reference="APPROVAL-PHASE51",
        security_approval_expires_at=expiry,
        reviewed_by="independent-reviewer",
        reviewed_at=now,
        observations=tuple(
            AcceptanceObservation(name, True, now, f"evidence/{name}")
            for name in sorted(REQUIRED_CASES)
        ),
    )
    return credentials, acceptance


def test_synthetic_complete_metadata_never_activates(records):
    result = inspect_staging_readiness(*records)
    assert result.ready_for_manual_security_review
    assert not result.live_customer_access_enabled
    assert not result.payments_enabled
    assert not result.production_activation_authorized


@pytest.mark.parametrize("field,value,error", [
    ("company_id", "9ff995dc-ad87-4a91-8a8f-18ddfc85d991", "identity:company_mismatch"),
    ("approved_test_borrower_id", "9ff995dc-ad87-4a91-8a8f-18ddfc85d992", "identity:borrower_mismatch"),
    ("security_approval_reference", "DIFFERENT-APPROVAL", "approval:reference_mismatch"),
])
def test_acceptance_cannot_cross_provisioning_boundary(records, field, value, error):
    credentials, acceptance = records
    result = inspect_staging_readiness(credentials, replace(acceptance, **{field: value}))
    assert not result.ready_for_manual_security_review
    assert error in result.failures


def test_approval_expiration_mismatch_rejected(records):
    credentials, acceptance = records
    acceptance = replace(
        acceptance, security_approval_expires_at=acceptance.security_approval_expires_at + timedelta(minutes=2)
    )
    assert "approval:expiry_mismatch" in inspect_staging_readiness(credentials, acceptance).failures


def test_insecure_mount_stops_readiness(records):
    credentials, acceptance = records
    from pathlib import Path
    Path(credentials.borrower_token_path).chmod(0o644)
    result = inspect_staging_readiness(credentials, acceptance)
    assert not result.ready_for_manual_security_review
    assert "credential:borrower_token_mount_insecure" in result.failures


def test_missing_acceptance_stops_readiness(records):
    credentials, _ = records
    result = inspect_staging_readiness(credentials, None)
    assert not result.ready_for_manual_security_review
    assert "acceptance:acceptance_evidence_missing" in result.failures


def test_missing_credentials_stops_readiness(records):
    _, acceptance = records
    result = inspect_staging_readiness(None, acceptance)
    assert not result.ready_for_manual_security_review
    assert "credential:manifest_missing" in result.failures


def test_failed_case_stops_readiness(records):
    credentials, acceptance = records
    observations = list(acceptance.observations)
    observations[0] = replace(observations[0], passed=False)
    result = inspect_staging_readiness(
        credentials, replace(acceptance, observations=tuple(observations))
    )
    assert not result.ready_for_manual_security_review
    assert "acceptance:case_failed" in result.failures
