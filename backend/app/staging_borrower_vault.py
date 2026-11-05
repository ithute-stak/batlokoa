"""Explicit, volatile Phase-49 staging vault for LoanHub borrower credentials.

NEVER bootstrapped by the public gateway. Intended only for isolated single-
process acceptance testing with approved synthetic/test borrower credentials.
No key generation, environment reads, login routes or external network calls.
A production vault requires persistent encrypted storage, envelope-key rotation,
session-to-link binding, distributed revocation and security approval.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken

from .loanhub_grant_broker import BorrowerAccountEvidence


@dataclass(frozen=True)
class _Entry:
    ciphertext: bytes
    central_sid: UUID
    expires_at: datetime


def _uuid(value: str | UUID) -> str:
    result = str(UUID(str(value)))
    if result != str(value):
        raise ValueError("Noncanonical UUID")
    return result


class EphemeralBorrowerTokenVault:
    """Bounded, encrypted, in-memory test-token vault; one Python process only.

    The approved caller must authenticate central_sid independently and must
    never accept a caller-selected tenant, borrower or SID as proof of linkage.
    A trusted LoanHub verifier runs BEFORE insertion, and again when the grant
    broker uses the released token. Revocation removes associated ciphertext.
    """

    def __init__(
        self, *,
        encryption_key: bytes,
        verify_token_for: Callable[[str, str, str], BorrowerAccountEvidence | None],
        max_entries: int = 64,
        max_ttl: timedelta = timedelta(minutes=5),
    ) -> None:
        if not callable(verify_token_for):
            raise ValueError("Trusted LoanHub verifier is required")
        if not isinstance(max_entries, int) or isinstance(max_entries, bool) or not 1 <= max_entries <= 256:
            raise ValueError("Staging vault capacity must be bounded")
        if not timedelta(seconds=10) <= max_ttl <= timedelta(minutes=5):
            raise ValueError("Staging vault token retention is limited to 5 minutes")
        self._cipher = Fernet(encryption_key)
        self._verify = verify_token_for
        self._max_entries = max_entries
        self._max_ttl = max_ttl
        self._lock = threading.RLock()
        self._entries: dict[tuple[str, str], _Entry] = {}
        self._revoked_sids: set[UUID] = set()

    @staticmethod
    def _trusted_proof(
        proof: BorrowerAccountEvidence | None, tenant: str, borrower: str, now: datetime
    ) -> bool:
        if not isinstance(proof, BorrowerAccountEvidence):
            return False
        if (proof.tenant_id != tenant or proof.borrower_id != borrower
                or proof.role != "borrower" or proof.account_active is not True
                or proof.session_active is not True):
            return False
        if (not isinstance(proof.verified_at, datetime) or proof.verified_at.tzinfo is None
                or not isinstance(proof.token_expires_at, datetime)
                or proof.token_expires_at.tzinfo is None):
            return False
        verified = proof.verified_at.astimezone(timezone.utc)
        expires = proof.token_expires_at.astimezone(timezone.utc)
        return (now - timedelta(seconds=1) <= verified <= now
                and expires > now + timedelta(seconds=2))

    @staticmethod
    def _token_ok(token: str) -> bool:
        return (isinstance(token, str) and 1 <= len(token) <= 8192
                and token.isascii() and not any(ch.isspace() for ch in token))

    def _purge(self, now: datetime) -> None:
        self._entries = {
            key: entry for key, entry in self._entries.items()
            if entry.expires_at > now and entry.central_sid not in self._revoked_sids
        }

    def provision(
        self, *, tenant_id: str, borrower_id: str,
        central_sid: UUID, token: str,
    ) -> bool:
        """Verify a server-approved mapping and encrypt; never persist plaintext."""
        try:
            tenant = _uuid(tenant_id)
            borrower = _uuid(borrower_id)
            if not isinstance(central_sid, UUID) or not self._token_ok(token):
                return False
            proof = self._verify(token, tenant, borrower)
            now = datetime.now(timezone.utc)
            if not self._trusted_proof(proof, tenant, borrower, now):
                return False
            expires = min(
                proof.token_expires_at.astimezone(timezone.utc), now + self._max_ttl
            )
            encrypted = self._cipher.encrypt(token.encode("ascii"))
            with self._lock:
                self._purge(datetime.now(timezone.utc))
                if central_sid in self._revoked_sids:
                    return False
                key = (tenant, borrower)
                if key not in self._entries and len(self._entries) >= self._max_entries:
                    return False
                # A new central identity may not overwrite a still-active
                # borrower's existing credential or claim that session.
                existing = self._entries.get(key)
                if existing is not None and existing.central_sid != central_sid:
                    return False
                self._entries[key] = _Entry(encrypted, central_sid, expires)
                return True
        except Exception:
            return False

    def token_for(self, tenant_id: str, borrower_id: str) -> str | None:
        """Backend broker input; verifier must recheck LoanHub on every use."""
        try:
            key = (_uuid(tenant_id), _uuid(borrower_id))
            with self._lock:
                now = datetime.now(timezone.utc)
                self._purge(now)
                entry = self._entries.get(key)
                if entry is None:
                    return None
                token = self._cipher.decrypt(entry.ciphertext).decode("ascii")
                return token if self._token_ok(token) else None
        except (ValueError, TypeError, UnicodeError, InvalidToken):
            return None

    def revoke_borrower(self, tenant_id: str, borrower_id: str) -> bool:
        """Operator-initiated removal of this exact tenant-bound grant."""
        try:
            key = (_uuid(tenant_id), _uuid(borrower_id))
            with self._lock:
                return self._entries.pop(key, None) is not None
        except (TypeError, ValueError):
            return False

    def revoke_central_session(self, central_sid: UUID) -> int:
        """Invalidate all borrowers linked to a previously authenticated SID."""
        if not isinstance(central_sid, UUID):
            return 0
        with self._lock:
            self._revoked_sids.add(central_sid)
            targets = [
                key for key, entry in self._entries.items()
                if entry.central_sid == central_sid
            ]
            for key in targets:
                del self._entries[key]
            return len(targets)

    def close(self) -> None:
        """Drop keys' reachable ciphertext references on staging shutdown."""
        with self._lock:
            self._entries.clear()
            self._revoked_sids.clear()
