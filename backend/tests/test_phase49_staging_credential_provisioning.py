"""Offline staging security tests: synthetic mounts, zero upstream traffic."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os

import pytest

from backend.app.staging_credential_provisioning import (
    StagingCredentialManifest,
    inspect_staging_credential_manifest,
)


@pytest.fixture
def manifest(tmp_path: Path):
    token = tmp_path / "borrower-token"
    public = tmp_path / "loanhub-public-key"
    token.write_text("FAKE_TOKEN_FOR_METADATA_ONLY_TEST")
    public.write_text("FAKE_PUBLIC_KEY_FOR_METADATA_ONLY_TEST")
    token.chmod(0o600)
    public.chmod(0o600)
    return StagingCredentialManifest(
        company_id="d921126e-e1a7-482e-ad1b-6e99b1682e19",
        loanhub_origin="https://loanhub-staging.example.invalid",
        borrower_token_path=str(token),
        loanhub_public_key_path=str(public),
        approved_test_borrower_id="cb6700f8-1808-46ca-bfc2-f030ad0e2d7c",
        approval_reference="STAGING-APPROVAL-49",
        approval_expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )


def test_secure_metadata_only_ready_but_never_activates_services(manifest):
    result = inspect_staging_credential_manifest(manifest)
    assert result.ready_for_operator_acceptance
    assert result.failures == ()
    assert result.live_customer_access_enabled is False
    assert result.payments_enabled is False


@pytest.mark.parametrize("field,value,reason", [
    ("environment", "production", "staging_environment_required"),
    ("live_customer_access_enabled", True, "live_customer_access_must_remain_disabled"),
    ("payments_enabled", True, "payments_must_remain_disabled"),
    ("company_id", "other", "company_id_invalid"),
    ("approved_test_borrower_id", "other", "test_borrower_id_invalid"),
    ("loanhub_origin", "http://loanhub.invalid", "loanhub_origin_invalid"),
    ("loanhub_origin", "https://user:pass@loanhub.invalid", "loanhub_origin_invalid"),
    ("approval_reference", "", "approval_reference_missing"),
    ("approval_expires_at", datetime(2020, 1, 1, tzinfo=timezone.utc), "approval_expired"),
])
def test_manifest_denials(manifest, field, value, reason):
    result = inspect_staging_credential_manifest(replace(manifest, **{field: value}))
    assert not result.ready_for_operator_acceptance
    assert reason in result.failures


def test_token_file_cannot_be_world_readable(manifest):
    token = Path(manifest.borrower_token_path)
    token.chmod(0o644)
    result = inspect_staging_credential_manifest(manifest)
    assert "borrower_token_mount_insecure" in result.failures


def test_token_file_cannot_be_symlink(manifest, tmp_path):
    target = Path(manifest.borrower_token_path)
    alias = tmp_path / "borrower-token-link"
    alias.symlink_to(target)
    result = inspect_staging_credential_manifest(
        replace(manifest, borrower_token_path=str(alias))
    )
    assert "borrower_token_mount_insecure" in result.failures


def test_missing_and_empty_mounts_fail(manifest, tmp_path):
    absent = replace(manifest, borrower_token_path=str(tmp_path / "missing"))
    assert "borrower_token_mount_insecure" in inspect_staging_credential_manifest(absent).failures
    Path(manifest.loanhub_public_key_path).write_text("")
    assert "loanhub_public_key_mount_insecure" in inspect_staging_credential_manifest(manifest).failures


def test_manifest_missing_fails_closed():
    result = inspect_staging_credential_manifest(None)
    assert not result.ready_for_operator_acceptance
    assert result.failures == ("manifest_missing",)
