"""Revocable, opaque same-origin Batlokoa BFF session persistence.

NOT registered in public FastAPI routes. A privileged bootstrap must first
verify a real !thute access token, check customer mapping, and separately
establish an authenticated LoanHub borrower session. No session here is a
LoanHub token and creating one never grants LoanHub read access automatically.

No browser tokens, access tokens or refresh tokens are stored in PostgreSQL.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import asyncpg

from .auth_verification import CentralAccessClaims
from .identity import CustomerContext


class SessionDenied(Exception):
    pass


@dataclass(frozen=True)
class SessionGrant:
    session_token: str
    csrf_token: str
    expires_at: datetime


@dataclass(frozen=True)
class ActiveSession:
    context: CustomerContext
    central_sid: UUID


def cookie_headers(grant: SessionGrant) -> tuple[str, str]:
    """Security cookie recommendation; HTTPS and a trusted same-origin BFF required.

    The CSRF value is returned separately for same-origin form/header use.
    Do not expose it in URLs or cross-origin pages.
    """
    lifetime = max(0, int((grant.expires_at - datetime.now(timezone.utc)).total_seconds()))
    return (
        f"__Host-batlokoa_session={grant.session_token}; Path=/; Max-Age={lifetime}; Secure; HttpOnly; SameSite=Strict",
        "Cache-Control: no-store",
    )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


class PostgresSessionStore:
    def __init__(self, pool: asyncpg.Pool, *, schema: str = "public") -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema):
            raise ValueError("Invalid database schema")
        self._pool = pool
        self._sessions = f'"{schema}".customer_sessions'
        self._links = f'"{schema}".customer_account_links'
        self._revocations = f'"{schema}".customer_central_session_revocations'

    async def issue(
        self, *, claims: CentralAccessClaims, tenant_id: UUID,
        ttl_seconds: int = 900,
    ) -> SessionGrant:
        """Only call after independent verified IdP authentication.

        Link is resolved transactionally by verified (iss,sub,tenant). The
        caller never supplies a browser-controlled borrower ID.
        """
        if (not 60 <= ttl_seconds <= 900 or not claims.iss.startswith("https://")
                or not claims.sub):
            raise SessionDenied("Invalid session context")
        try:
            central_sid = UUID(claims.sid)
        except ValueError as exc:
            raise SessionDenied("Invalid verified session ID") from exc
        now = datetime.now(timezone.utc)
        if claims.exp <= int(now.timestamp()):
            raise SessionDenied("Expired identity proof")
        expiry = min(
            now + timedelta(seconds=ttl_seconds),
            datetime.fromtimestamp(claims.exp, tz=timezone.utc),
        )
        if expiry <= now + timedelta(seconds=1):
            raise SessionDenied("Identity proof is about to expire")
        raw_token = secrets.token_urlsafe(48)
        raw_csrf = secrets.token_urlsafe(32)
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    str(central_sid),
                )
                if await connection.fetchval(
                    f"SELECT 1 FROM {self._revocations} WHERE central_sid=$1",
                    central_sid,
                ):
                    raise SessionDenied("Central identity session has been revoked")
                link_id = await connection.fetchval(
                    f"""SELECT id FROM {self._links}
                        WHERE issuer=$1 AND subject=$2 AND tenant_id=$3
                        AND revoked_at IS NULL
                        FOR SHARE""",
                    claims.iss, claims.sub, tenant_id,
                )
                if link_id is None:
                    raise SessionDenied("No active customer link")
                await connection.execute(
                    f"""INSERT INTO {self._sessions}
                    (id, link_id, central_sid, token_sha256, csrf_sha256, expires_at)
                    VALUES ($1,$2,$3,$4,$5,$6)""",
                    uuid4(), link_id, central_sid,
                    _digest(raw_token), _digest(raw_csrf), expiry,
                )
        return SessionGrant(raw_token, raw_csrf, expiry)

    async def resolve(
        self, token: str, *, csrf_token: str | None = None,
        require_csrf: bool = False,
    ) -> ActiveSession | None:
        if (not isinstance(token, str) or not 32 <= len(token) <= 256
                or not token.isascii()):
            return None
        if require_csrf and (not isinstance(csrf_token, str) or
                             not 24 <= len(csrf_token) <= 256 or
                             not csrf_token.isascii()):
            return None
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""SELECT l.issuer,l.subject,l.tenant_id,l.borrower_id,
                           s.central_sid,s.csrf_sha256
                FROM {self._sessions} s
                JOIN {self._links} l ON l.id=s.link_id
                WHERE s.token_sha256=$1 AND s.revoked_at IS NULL
                AND s.expires_at > now() AND l.revoked_at IS NULL
                AND NOT EXISTS (
                    SELECT 1 FROM {self._revocations} r
                    WHERE r.central_sid=s.central_sid
                )""",
                _digest(token),
            )
        if row is None:
            return None
        if require_csrf and not hmac.compare_digest(
            row["csrf_sha256"], _digest(csrf_token)
        ):
            return None
        return ActiveSession(
            context=CustomerContext(
                tenant_id=str(row["tenant_id"]),
                customer_id=str(row["borrower_id"]),
                auth_subject=row["subject"],
            ),
            central_sid=row["central_sid"],
        )

    async def revoke(self, token: str) -> bool:
        if (not isinstance(token, str) or not 32 <= len(token) <= 256
                or not token.isascii()):
            return False
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""UPDATE {self._sessions} SET revoked_at=now()
                WHERE token_sha256=$1 AND revoked_at IS NULL
                RETURNING id""",
                _digest(token),
            )
        return row is not None

    async def revoke_central_session(self, sid: UUID) -> int:
        """Only call after an authenticated central Auth revocation event."""
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    str(sid),
                )
                await connection.execute(
                    f"""INSERT INTO {self._revocations}(central_sid)
                    VALUES ($1) ON CONFLICT (central_sid) DO NOTHING""",
                    sid,
                )
                result = await connection.execute(
                    f"""UPDATE {self._sessions} SET revoked_at=now()
                    WHERE central_sid=$1 AND revoked_at IS NULL""",
                    sid,
                )
        return int(result.split()[-1])
