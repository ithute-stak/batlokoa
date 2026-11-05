"""Phase 49: offline, fail-closed checks for staging secret mounts.

Never reads secret bytes, validates token contents, calls LoanHub, or enables routes.
The operator must independently approve and verify actual borrower acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import os
import stat
from urllib.parse import urlsplit
from uuid import UUID


@dataclass(frozen=True)
class StagingCredentialManifest:
    company_id: str
    loanhub_origin: str
    borrower_token_path: str
    loanhub_public_key_path: str
    approved_test_borrower_id: str
    approval_reference: str
    approval_expires_at: datetime
    environment: str = "staging"
    live_customer_access_enabled: bool = False
    payments_enabled: bool = False


@dataclass(frozen=True)
class StagingProvisioningResult:
    ready_for_operator_acceptance: bool
    failures: tuple[str, ...]
    live_customer_access_enabled: bool = False
    payments_enabled: bool = False


def _canonical_uuid(value: str) -> bool:
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except (TypeError, ValueError, AttributeError):
        return False


def _valid_https_origin(value: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        url = urlsplit(value)
        return (url.scheme == "https" and bool(url.hostname)
                and not url.username and not url.password
                and url.path in ("", "/") and not url.query and not url.fragment
                and url.port != 0)
    except ValueError:
        return False


def _secure_regular_file(path_text: str, *, sensitive: bool) -> bool:
    """Check mount metadata only; never open credential files."""
    if not isinstance(path_text, str) or not path_text:
        return False
    try:
        path = Path(path_text)
        if not path.is_absolute():
            return False
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            return False  # also denies symlinks, sockets and directory mounts
        if not 1 <= metadata.st_size <= 8192:
            return False
        if metadata.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            return False
        if sensitive and metadata.st_mode & stat.S_IXUSR:
            return False
        if metadata.st_uid not in (os.geteuid(), 0):
            return False
        return True
    except (OSError, ValueError, TypeError):
        return False


def inspect_staging_credential_manifest(
    manifest: StagingCredentialManifest | None,
    *,
    now: datetime | None = None,
) -> StagingProvisioningResult:
    """Metadata-only preflight, not a credential or production authorization."""
    if not isinstance(manifest, StagingCredentialManifest):
        return StagingProvisioningResult(False, ("manifest_missing",))
    failures: list[str] = []
    if manifest.environment != "staging":
        failures.append("staging_environment_required")
    if manifest.live_customer_access_enabled is not False:
        failures.append("live_customer_access_must_remain_disabled")
    if manifest.payments_enabled is not False:
        failures.append("payments_must_remain_disabled")
    if not _canonical_uuid(manifest.company_id):
        failures.append("company_id_invalid")
    if not _canonical_uuid(manifest.approved_test_borrower_id):
        failures.append("test_borrower_id_invalid")
    if not _valid_https_origin(manifest.loanhub_origin):
        failures.append("loanhub_origin_invalid")
    if not _secure_regular_file(manifest.borrower_token_path, sensitive=True):
        failures.append("borrower_token_mount_insecure")
    if not _secure_regular_file(manifest.loanhub_public_key_path, sensitive=False):
        failures.append("loanhub_public_key_mount_insecure")
    if (not isinstance(manifest.approval_reference, str)
            or not 8 <= len(manifest.approval_reference.strip()) <= 120):
        failures.append("approval_reference_missing")
    current = now or datetime.now(timezone.utc)
    if (not isinstance(current, datetime) or current.tzinfo is None
            or not isinstance(manifest.approval_expires_at, datetime)
            or manifest.approval_expires_at.tzinfo is None
            or manifest.approval_expires_at.astimezone(timezone.utc)
                <= current.astimezone(timezone.utc)):
        failures.append("approval_expired")
    return StagingProvisioningResult(
        ready_for_operator_acceptance=not failures,
        failures=tuple(failures),
    )
