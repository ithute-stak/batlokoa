"""Phase 43 configuration checks never activate live integrations."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.loanhub_integration_preflight import (
    ControlledLoanHubIntegration,
    inspect_loanhub_integration,
)

TENANT = "d921126e-e1a7-482e-ad1b-6e99b1682e19"


def approved(tmp_path):
    key = tmp_path / "loanhub-public.pem"
    key.write_text("test-public-key-metadata-only")
    key.chmod(0o600)
    return ControlledLoanHubIntegration(
        tenant_id=TENANT,
        loanhub_origin="https://loanhub.example.test",
        batlokoa_origin="https://batlokoa.example.test",
        public_key_path=str(key),
        borrower_token_vault_configured=True,
        borrower_mapping_reader_configured=True,
        borrower_mapping_read_only_verified=True,
        loanhub_revocation_verified=True,
        security_approval_reference="SECURITY-APPROVAL-CI",
        security_approval_expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )


def test_missing_configuration_fails_closed_and_no_activation():
    report = inspect_loanhub_integration(None)
    assert not report.checks_passed and not report.production_enabled
    assert report.failures == ("integration_configuration_missing",)


def test_all_metadata_checks_never_activate_live_customer_routes(tmp_path):
    report = inspect_loanhub_integration(approved(tmp_path))
    assert report.checks_passed and not report.failures
    assert report.production_enabled is False


@pytest.mark.parametrize("field,value,expected", [
    ("tenant_id", "another-company", "approved_tenant_invalid"),
    ("loanhub_origin", "http://loanhub.example.test", "loanhub_https_origin_invalid"),
    ("loanhub_origin", "https://user:pass@loanhub.example.test", "loanhub_https_origin_invalid"),
    ("loanhub_origin", "https://[invalid", "loanhub_https_origin_invalid"),
    ("loanhub_origin", "https://loanhub.example.test/api", "loanhub_https_origin_invalid"),
    ("batlokoa_origin", "http://batlokoa.example.test", "batlokoa_https_origin_invalid"),
    ("borrower_token_vault_configured", False, "borrower_token_vault_configured_missing"),
    ("borrower_mapping_reader_configured", False, "borrower_mapping_reader_configured_missing"),
    ("borrower_mapping_read_only_verified", False, "borrower_mapping_read_only_verified_missing"),
    ("loanhub_revocation_verified", False, "loanhub_revocation_verified_missing"),
    ("security_approval_reference", "", "security_approval_missing"),
    ("security_approval_expires_at", datetime.now(timezone.utc) - timedelta(days=1), "security_approval_expired"),
    ("security_approval_expires_at", datetime.now(), "security_approval_expired"),
])
def test_invalid_evidence_is_rejected_without_activating(tmp_path, field, value, expected):
    report = inspect_loanhub_integration(replace(approved(tmp_path), **{field: value}))
    assert not report.checks_passed
    assert expected in report.failures
    assert report.production_enabled is False


def test_missing_or_symlinked_or_world_writable_public_key_fails(tmp_path):
    config = approved(tmp_path)
    key = tmp_path / "loanhub-public.pem"
    key.chmod(0o666)
    assert "trusted_public_key_file_unusable" in inspect_loanhub_integration(config).failures
    key.chmod(0o600)
    alias = tmp_path / "alias.pem"
    alias.symlink_to(key)
    assert "trusted_public_key_file_unusable" in inspect_loanhub_integration(
        replace(config, public_key_path=str(alias))).failures
    key.unlink()
    assert "trusted_public_key_file_unusable" in inspect_loanhub_integration(config).failures


def test_same_origin_not_accepted(tmp_path):
    config = approved(tmp_path)
    report = inspect_loanhub_integration(
        replace(config, loanhub_origin=config.batlokoa_origin))
    assert not report.checks_passed
    assert "origins_not_separated" in report.failures


def test_configuration_cannot_change_runtime_flags(tmp_path):
    from backend.app.main import app

    if hasattr(app.state, "session_loan_read_config"):
        del app.state.session_loan_read_config
    if hasattr(app.state, "customer_loan_read_config"):
        del app.state.customer_loan_read_config

    assert inspect_loanhub_integration(approved(tmp_path)).checks_passed
    assert not hasattr(app.state, "session_loan_read_config")
    assert not hasattr(app.state, "customer_loan_read_config")
