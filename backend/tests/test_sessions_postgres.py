"""Actual PostgreSQL tests for opaque Batlokoa BFF session lifecycle.

The tests use disposable schemas and never issue a real customer session.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4
import os

import asyncpg
import pytest
import pytest_asyncio

from backend.app.auth_verification import CentralAccessClaims
from backend.app.link_store import PostgresCustomerLinkStore
from backend.app.sessions import PostgresSessionStore, SessionDenied, cookie_headers

URL = os.getenv("BATLOKOA_LINK_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Disposable PostgreSQL URL absent")
ISSUER = "https://auth.ithute.co.ls"
TENANT = UUID("d921126e-e1a7-482e-ad1b-6e99b1682e19")
BORROWER = UUID("cb6700f8-1808-46ca-bfc2-f030ad0e2d7c")
CENTRAL_SID = uuid4()


@pytest_asyncio.fixture
async def stores():
    schema = "test_session_" + uuid4().hex[:14]
    admin = await asyncpg.connect(URL)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    try:
        for name in ("001_customer_account_links.sql", "002_customer_sessions.sql"):
            sql = Path("backend/migrations", name).read_text()
            await admin.execute(sql.replace('"public".', f'"{schema}".'))
        pool = await asyncpg.create_pool(URL, min_size=1, max_size=3)
        try:
            links = PostgresCustomerLinkStore(pool, schema=schema)
            sessions = PostgresSessionStore(pool, schema=schema)
            yield links, sessions, pool, schema
        finally:
            await pool.close()
    finally:
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()


def claims(*, expires_in=300, subject="central-uuid-subject"):
    now = datetime.now(timezone.utc)
    return CentralAccessClaims(
        iss=ISSUER, aud="batlokoa", sub=subject, sid=str(CENTRAL_SID),
        iat=int(now.timestamp()), exp=int((now+timedelta(seconds=expires_in)).timestamp()),
        token_use="access",
    )


async def linked(links, *, subject="central-uuid-subject"):
    return await links.bind_once(
        issuer=ISSUER, subject=subject, tenant_id=TENANT,
        borrower_id=BORROWER, proof_id="session-test-proof",
        consent_reference="session-test-consent",
    )


@pytest.mark.asyncio
async def test_issue_resolve_csrf_revoke_no_plaintext_in_database(stores):
    links, sessions, pool, schema = stores
    await linked(links)
    grant = await sessions.issue(claims=claims(), tenant_id=TENANT)
    assert grant.session_token != grant.csrf_token
    assert grant.expires_at <= datetime.now(timezone.utc) + timedelta(minutes=5)
    active = await sessions.resolve(grant.session_token)
    assert active is not None
    assert active.context.tenant_id == str(TENANT)
    assert active.context.customer_id == str(BORROWER)
    assert active.central_sid == CENTRAL_SID
    assert await sessions.resolve(grant.session_token, require_csrf=True) is None
    assert await sessions.resolve(
        grant.session_token, csrf_token="wrong-csrf-token-long-enough",
        require_csrf=True,
    ) is None
    assert await sessions.resolve(
        grant.session_token, csrf_token=grant.csrf_token,
        require_csrf=True,
    ) == active
    cookie, cache = cookie_headers(grant)
    assert "Secure; HttpOnly; SameSite=Strict" in cookie
    assert "__Host-batlokoa_session=" in cookie
    assert cache == "Cache-Control: no-store"
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            f'SELECT token_sha256, csrf_sha256 FROM "{schema}".customer_sessions'
        )
        assert row["token_sha256"] != grant.session_token
        assert row["csrf_sha256"] != grant.csrf_token
    assert await sessions.revoke(grant.session_token)
    assert await sessions.resolve(grant.session_token) is None
    assert not await sessions.revoke(grant.session_token)


@pytest.mark.asyncio
async def test_unlinked_customer_cannot_issue_session(stores):
    _, sessions, _, _ = stores
    with pytest.raises(SessionDenied):
        await sessions.issue(claims=claims(), tenant_id=TENANT)


@pytest.mark.asyncio
async def test_revoked_account_invalidates_all_existing_sessions(stores):
    links, sessions, _, _ = stores
    await linked(links)
    grant = await sessions.issue(claims=claims(), tenant_id=TENANT)
    assert await sessions.resolve(grant.session_token) is not None
    assert await links.revoke_self(
        issuer=ISSUER, subject="central-uuid-subject",
        tenant_id=TENANT, reason="Customer requested account unlinking",
    )
    assert await sessions.resolve(grant.session_token) is None
    with pytest.raises(SessionDenied):
        await sessions.issue(claims=claims(), tenant_id=TENANT)


@pytest.mark.asyncio
async def test_central_sid_revocation_kills_all_associated_sessions(stores):
    links, sessions, _, _ = stores
    await linked(links)
    a = await sessions.issue(claims=claims(), tenant_id=TENANT)
    b = await sessions.issue(claims=claims(), tenant_id=TENANT)
    assert await sessions.revoke_central_session(CENTRAL_SID) == 2
    assert await sessions.resolve(a.session_token) is None
    assert await sessions.resolve(b.session_token) is None
    assert await sessions.revoke_central_session(CENTRAL_SID) == 0


@pytest.mark.asyncio
async def test_session_expiration_checked_at_database_read(stores):
    links, sessions, pool, schema = stores
    await linked(links)
    grant = await sessions.issue(claims=claims(), tenant_id=TENANT)
    async with pool.acquire() as connection:
        await connection.execute(
            f'UPDATE "{schema}".customer_sessions SET expires_at=now() - interval \'1 minute\''
        )
    assert await sessions.resolve(grant.session_token) is None


@pytest.mark.asyncio
async def test_short_expiry_and_untrusted_config_rejected(stores):
    links, sessions, _, _ = stores
    await linked(links)
    with pytest.raises(SessionDenied):
        await sessions.issue(claims=claims(expires_in=-5), tenant_id=TENANT)
    with pytest.raises(SessionDenied):
        await sessions.issue(claims=claims(), tenant_id=TENANT, ttl_seconds=3600)
    with pytest.raises(SessionDenied):
        await sessions.issue(claims=claims(), tenant_id=uuid4())
