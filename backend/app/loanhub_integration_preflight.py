"""Offline, non-activating readiness preflight for LoanHub borrower reads.

This module never connects to LoanHub, reads credential values, enables
FastAPI routes or infers production approval from passing local checks.
It checks the *presence* of reviewed configuration and evidence only.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID
import stat


@dataclass(frozen=True)
class ControlledLoanHubIntegration:
    tenant_id: str
    loanhub_origin: str
    batlokoa_origin: str
    public_key_path: str
    borrower_token_vault_configured: bool
    borrower_mapping_reader_configured: bool
    borrower_mapping_read_only_verified: bool
    loanhub_revocation_verified: bool
    security_approval_reference: str
    security_approval_expires_at: datetime


@dataclass(frozen=True)
class IntegrationPreflight:
    checks_passed: bool
    failures: tuple[str, ...]
    production_enabled: bool = False


def _https_origin(value: str) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.path in ("", "/")
        and not parsed.username and not parsed.password
        and not parsed.query and not parsed.fragment
        and not parsed.netloc.endswith(":")
    )


def inspect_loanhub_integration(
    config: ControlledLoanHubIntegration | None,
    *,
    require_distinct_origins: bool = True,
) -> IntegrationPreflight:
    """Validate operator evidence; never mutate state or read private secrets."""
    failures: list[str] = []
    if not isinstance(config, ControlledLoanHubIntegration):
        return IntegrationPreflight(False, ("integration_configuration_missing",))

    try:
        if str(UUID(config.tenant_id)) != config.tenant_id:
            failures.append("approved_tenant_invalid")
    except (ValueError, TypeError, AttributeError):
        failures.append("approved_tenant_invalid")

    if not _https_origin(config.loanhub_origin):
        failures.append("loanhub_https_origin_invalid")
    if not _https_origin(config.batlokoa_origin):
        failures.append("batlokoa_https_origin_invalid")
    if (require_distinct_origins and
            config.loanhub_origin == config.batlokoa_origin):
        failures.append("origins_not_separated")

    # Only inspect metadata. Never open the key, disclose its contents or
    # infer trust in the operator's public key from its presence alone.
    try:
        path = Path(config.public_key_path)
        if (not path.is_absolute() or path.is_symlink() or
                not path.is_file() or path.stat().st_size == 0 or
                path.stat().st_size > 8192 or
                path.stat().st_mode & (stat.S_IWGRP | stat.S_IWOTH)):
            failures.append("trusted_public_key_file_unusable")
    except (OSError, TypeError, ValueError):
        failures.append("trusted_public_key_file_unusable")

    for name in (
        "borrower_token_vault_configured",
        "borrower_mapping_reader_configured",
        "borrower_mapping_read_only_verified",
        "loanhub_revocation_verified",
    ):
        if getattr(config, name) is not True:
            failures.append(name + "_missing")

    if (not isinstance(config.security_approval_reference, str) or
            not 8 <= len(config.security_approval_reference.strip()) <= 120):
        failures.append("security_approval_missing")
    expiry = config.security_approval_expires_at
    if (not isinstance(expiry, datetime) or expiry.tzinfo is None or
            expiry.astimezone(timezone.utc) <= datetime.now(timezone.utc)):
        failures.append("security_approval_expired")

    # Even after all checks pass, actual production activation requires an
    # independently reviewed bootstrap outside this preflight.
    return IntegrationPreflight(
        checks_passed=not failures,
        failures=tuple(failures),
        production_enabled=False,
    )
