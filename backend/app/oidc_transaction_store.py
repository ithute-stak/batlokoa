"""Database-backed one-use OIDC transaction store.

No runtime connection is created here. Encryption key must be supplied through
an approved server secret manager (NOT stored in the database or repository).
Deleting and returning the row in one statement prevents replay even when
multiple gateway instances receive a callback concurrently.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

import asyncpg
from cryptography.fernet import Fernet, InvalidToken

from .oidc_login import LoginDenied, PendingLogin


class PostgresOidcTransactionStore:
    def __init__(self, pool: asyncpg.Pool, *, encryption_key: bytes,
                 schema: str = "public") -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema):
            raise ValueError("Invalid OIDC store schema")
        self._fernet = Fernet(encryption_key)
        self._pool = pool
        self._table = f'"{schema}".oidc_login_transactions'

    @staticmethod
    def _digest(state: str) -> str:
        return hashlib.sha256(state.encode("ascii")).hexdigest()

    async def save(self, transaction: PendingLogin, *, expires_seconds: int) -> None:
        if (not 30 <= expires_seconds <= 300 or
                not all(isinstance(value, str) and 32 <= len(value) <= 256
                        and value.isascii() for value in
                        (transaction.state, transaction.nonce, transaction.code_verifier))):
            raise LoginDenied("Invalid login transaction")
        payload = json.dumps({
            "nonce": transaction.nonce,
            "verifier": transaction.code_verifier,
        }, separators=(",", ":")).encode("utf-8")
        cipher = self._fernet.encrypt(payload)
        expires = datetime.now(timezone.utc) + timedelta(seconds=expires_seconds)
        async with self._pool.acquire() as connection:
            await connection.execute(
                f"""INSERT INTO {self._table}
                  (state_sha256, encrypted_payload, expires_at)
                  VALUES ($1,$2,$3)""",
                self._digest(transaction.state), cipher, expires,
            )

    async def consume(self, *, state: str) -> PendingLogin | None:
        if not isinstance(state, str) or not 32 <= len(state) <= 256 or not state.isascii():
            return None
        # Deletes expired state too, but never returns its evidence.
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""DELETE FROM {self._table} WHERE state_sha256=$1
                    RETURNING encrypted_payload, expires_at""",
                self._digest(state),
            )
        if row is None or row["expires_at"] <= datetime.now(timezone.utc):
            return None
        try:
            payload = json.loads(self._fernet.decrypt(bytes(row["encrypted_payload"])))
            nonce = payload["nonce"]
            verifier = payload["verifier"]
            if not (isinstance(nonce, str) and isinstance(verifier, str) and
                    32 <= len(nonce) <= 256 and 32 <= len(verifier) <= 256):
                return None
            return PendingLogin(state=state, nonce=nonce, code_verifier=verifier)
        except (InvalidToken, ValueError, KeyError, TypeError):
            return None
