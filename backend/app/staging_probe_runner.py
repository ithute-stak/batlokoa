"""Phase 53: operator-invoked secret-mount reader for the Phase 52 probe.

Not registered in the public gateway. Never writes credentials, performs
revocation, records borrower data, or activates customer or payment routes.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Awaitable, Callable

from cryptography.hazmat.primitives import serialization

from .staging_credential_provisioning import (
    StagingCredentialManifest, inspect_staging_credential_manifest,
)
from .staging_loanhub_probe import (
    ProbeOutcome, ProbeResult, probe_approved_staging_borrower,
)

Probe = Callable[..., Awaitable[ProbeResult]]


def _read_protected_file(path: str) -> bytes:
    """Defend against a replaced symlink between preflight and file read."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("platform_missing_nofollow")
    descriptor = os.open(path, flags | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or
                info.st_mode & (stat.S_IRWXG | stat.S_IRWXO) or
                info.st_mode & stat.S_IXUSR or
                info.st_uid not in (os.geteuid(), 0) or
                not 1 <= info.st_size <= 8192):
            raise ValueError("untrusted_mount")
        data = os.read(descriptor, 8193)
        if len(data) != info.st_size:
            raise ValueError("mount_changed")
        return data
    finally:
        os.close(descriptor)


async def run_approved_staging_probe(
    *,
    manifest: StagingCredentialManifest | None,
    allowlisted_staging_origin: str,
    production_origin: str,
    operator_approved: bool,
    probe: Probe = probe_approved_staging_borrower,
) -> ProbeResult:
    """Run a single, read-only authorized test using private credential mounts.

    The origin allowlist must come from independently reviewed deployment
    configuration, never user input or the public website. No values are logged.
    """
    denied = ProbeResult(ProbeOutcome.INVALID_STAGING_SCOPE)
    if (operator_approved is not True or
            not isinstance(manifest, StagingCredentialManifest)):
        return denied
    if (not isinstance(allowlisted_staging_origin, str)
            or not isinstance(production_origin, str)
            or not production_origin
            or manifest.loanhub_origin != allowlisted_staging_origin
            or manifest.loanhub_origin.rstrip("/") == production_origin.rstrip("/")):
        return denied
    if not inspect_staging_credential_manifest(manifest).checks_passed if False else False:
        return denied
    if not inspect_staging_credential_manifest(manifest).ready_for_operator_acceptance:
        return denied
    try:
        token_bytes = _read_protected_file(manifest.borrower_token_path)
        public_key_bytes = _read_protected_file(manifest.loanhub_public_key_path)
        token = token_bytes.decode("ascii")
        if (not token or len(token) > 8192 or
                any(char.isspace() for char in token)):
            return ProbeResult(ProbeOutcome.AUTHORIZATION_DENIED)
        public_key = serialization.load_pem_public_key(public_key_bytes)
        return await probe(
            loanhub_origin=manifest.loanhub_origin,
            approved_origin=allowlisted_staging_origin,
            company_id=manifest.company_id,
            borrower_id=manifest.approved_test_borrower_id,
            borrower_access_token=token,
            trusted_public_key=public_key,
            approved_staging=True,
        )
    except Exception:
        # Do not echo filesystem paths, key material, JWT or upstream response.
        return ProbeResult(ProbeOutcome.AUTHORIZATION_DENIED)
