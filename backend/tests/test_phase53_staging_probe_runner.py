"""Phase 53: private mounts and explicit deployment guardrails."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from backend.app.staging_credential_provisioning import StagingCredentialManifest
from backend.app.staging_loanhub_probe import ProbeOutcome, ProbeResult
from backend.app.staging_probe_runner import run_approved_staging_probe

ORIGIN = "https://isolated-staging.invalid"
PRODUCTION = "https://loanhub-production.invalid"


@pytest.fixture
def manifest(tmp_path: Path):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_bytes = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    token = tmp_path / "staging-token"
    key = tmp_path / "approved-public-key"
    token.write_text("synthetic.token.only")
    key.write_bytes(public_bytes)
    token.chmod(0o600)
    key.chmod(0o600)
    return StagingCredentialManifest(
        company_id="d921126e-e1a7-482e-ad1b-6e99b1682e19",
        loanhub_origin=ORIGIN,
        borrower_token_path=str(token),
        loanhub_public_key_path=str(key),
        approved_test_borrower_id="cb6700f8-1808-46ca-bfc2-f030ad0e2d7c",
        approval_reference="SECURITY-APPROVAL-53",
        approval_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )


@pytest.mark.asyncio
async def test_authorized_staging_mount_passes_to_read_only_probe(manifest):
    observed = []
    async def synthetic_probe(**kwargs):
        observed.append(kwargs)
        return ProbeResult(ProbeOutcome.VERIFIED_READ_ONLY)
    result = await run_approved_staging_probe(
        manifest=manifest,
        allowlisted_staging_origin=ORIGIN,
        production_origin=PRODUCTION,
        operator_approved=True,
        probe=synthetic_probe,
    )
    assert result.outcome == ProbeOutcome.VERIFIED_READ_ONLY
    assert len(observed) == 1
    assert observed[0]["company_id"] == manifest.company_id
    assert observed[0]["borrower_access_token"] == "synthetic.token.only"
    assert not result.customer_access_enabled and not result.payments_enabled


@pytest.mark.asyncio
@pytest.mark.parametrize("operator,allowlist,production", [
    (False, ORIGIN, PRODUCTION),
    (True, "https://other-staging.invalid", PRODUCTION),
    (True, ORIGIN, ORIGIN),
    (True, ORIGIN, ""),
])
async def test_unapproved_scope_never_reads_or_calls_probe(
    manifest, monkeypatch, operator, allowlist, production,
):
    async def forbidden(**_kwargs):
        raise AssertionError("must never invoke probe")
    result = await run_approved_staging_probe(
        manifest=manifest, allowlisted_staging_origin=allowlist,
        production_origin=production, operator_approved=operator,
        probe=forbidden,
    )
    assert result.outcome == ProbeOutcome.INVALID_STAGING_SCOPE


@pytest.mark.asyncio
async def test_insecure_mount_fails_without_network(manifest):
    Path(manifest.borrower_token_path).chmod(0o644)
    called = False
    async def forbidden(**_kwargs):
        nonlocal called
        called = True
        return ProbeResult(ProbeOutcome.VERIFIED_READ_ONLY)
    result = await run_approved_staging_probe(
        manifest=manifest, allowlisted_staging_origin=ORIGIN,
        production_origin=PRODUCTION, operator_approved=True,
        probe=forbidden,
    )
    assert result.outcome == ProbeOutcome.INVALID_STAGING_SCOPE
    assert not called


@pytest.mark.asyncio
async def test_symlink_mount_rejected(manifest, tmp_path):
    alias = tmp_path / "alias"
    alias.symlink_to(manifest.borrower_token_path)
    result = await run_approved_staging_probe(
        manifest=replace(manifest, borrower_token_path=str(alias)),
        allowlisted_staging_origin=ORIGIN,
        production_origin=PRODUCTION, operator_approved=True,
    )
    assert result.outcome == ProbeOutcome.INVALID_STAGING_SCOPE
