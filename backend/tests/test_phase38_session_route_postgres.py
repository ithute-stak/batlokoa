"""Real PostgreSQL integration tests for disabled-by-default session loan reads.

A disposable schema, signed-in *simulated* central claims and a fake upstream
prove that the HTTP boundary uses the database's current link/revocation state.
No production identity provider, LoanHub or customer credentials are used.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
import pytest_asyncio

from backend.app.auth_verification import CentralAccessClaims
from backend.app.auth_routes import SESSION_COOKIE
from backend.app.contracts import LoanSummary, Money
from backend.app.identity import NoCustomersDirectory
from backend.app.link_store import PostgresCustomerLinkStore
from backend.app.loan_reads import LoanReadService
from backend.app.main import app
from backend.app.session_loan_reads import SessionLoanReadConfig
from backend.app.sessions import PostgresSessionStore

URL = os.getenv("BATLOKOA_LINK_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Disposable PostgreSQL URL not configured")
ISSUER = "https://auth.example.test"
ORIGIN = "https://batlokoa.example.test"
TENANT = UUID("d921126e-e1a7-482e-ad1b-6e99b1682e19")
BORROWER = UUID("cb6700f8-1808-46ca-bfc2-f030ad0e2d7c")
SUBJECT = "verified-test-subject"


class LoanHubStub:
    def __init__(self):
        self.calls = []
        self.fail = False

    async def list_customer_loans(self, *, tenant_id, customer_id):
        self.calls.append((tenant_id, customer_id))
        if self.fail:
            raise RuntimeError("fake-upstream-sensitive-error")
        return [LoanSummary(
            loan_id="controlled-test-loan",
            status="active",
            outstanding=Money(currency="LSL", minor_units=580005),
        )]


@pytest_asyncio.fixture
async def environment():
    schema = "test_route_" + uuid4().hex[:16]
    connection = await asyncpg.connect(URL)
    await connection.execute(f'CREATE SCHEMA "{schema}"')
    try:
        for filename in ("001_customer_account_links.sql", "002_customer_sessions.sql"):
            migration = Path("backend/migrations", filename).read_text()
            await connection.execute(
                migration.replace('"public".', f'"{schema}".'))
        pool = await asyncpg.create_pool(URL, min_size=1, max_size=4)
        try:
            links = PostgresCustomerLinkStore(pool, schema=schema)
            sessions = PostgresSessionStore(pool, schema=schema)
            stub = LoanHubStub()
            app.state.session_loan_read_config = SessionLoanReadConfig(
                sessions=sessions,
                service=LoanReadService(
                    tenant_id=str(TENANT),
                    directory=NoCustomersDirectory(),
                    adapter=stub,
                ),
                public_origin=ORIGIN,
            )
            try:
                yield links, sessions, stub, pool, schema
            finally:
                if hasattr(app.state, "session_loan_read_config"):
                    del app.state.session_loan_read_config
        finally:
            await pool.close()
    finally:
        await connection.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await connection.close()


def claims(*, sid):
    now = datetime.now(timezone.utc)
    return CentralAccessClaims(
        iss=ISSUER, aud="batlokoa", sub=SUBJECT, sid=str(sid),
        iat=int(now.timestamp()),
        exp=int((now + timedelta(minutes=5)).timestamp()),
        token_use="access",
    )


async def issue(links, sessions, *, sid):
    await links.bind_once(
        issuer=ISSUER, subject=SUBJECT, tenant_id=TENANT,
        borrower_id=BORROWER,
        proof_id="phase38-proof",
        consent_reference="phase38-consent",
    )
    return await sessions.issue(claims=claims(sid=sid), tenant_id=TENANT)


async def get_loans(token, *, headers=None):
    request_headers = {"Sec-Fetch-Site": "same-origin"}
    request_headers.update(headers or {})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=ORIGIN) as client:
        return await client.get(
            "/api/v1/me/loans/session",
            headers=request_headers,
            cookies={SESSION_COOKIE: token} if token else None,
        )


@pytest.mark.asyncio
async def test_real_db_session_allows_only_mapped_tenant_borrower(environment):
    links, sessions, stub, _, _ = environment
    grant = await issue(links, sessions, sid=uuid4())
    response = await get_loans(grant.session_token, headers={
        "Origin": ORIGIN,
        "X-Tenant-Id": "spoofed-other-tenant",
        "X-Customer-Id": "spoofed-other-borrower",
    })
    assert response.status_code == 200
    assert response.json()["loans"][0]["outstanding"]["minor_units"] == 580005
    assert response.headers["cache-control"] == "no-store"
    assert stub.calls == [(str(TENANT), str(BORROWER))]


@pytest.mark.asyncio
async def test_logout_revocation_blocks_followup_loan_reads(environment):
    links, sessions, stub, _, _ = environment
    grant = await issue(links, sessions, sid=uuid4())
    assert (await get_loans(grant.session_token)).status_code == 200
    assert await sessions.revoke(grant.session_token)
    response = await get_loans(grant.session_token)
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"
    assert stub.calls == [(str(TENANT), str(BORROWER))]


@pytest.mark.asyncio
async def test_central_revocation_marker_blocks_stale_unrevoked_db_session(environment):
    links, sessions, stub, pool, schema = environment
    sid = uuid4()
    grant = await issue(links, sessions, sid=sid)
    assert (await get_loans(grant.session_token)).status_code == 200
    # Simulate a revocation marker being written before individual sessions
    # are marked: the Phase 37 anti-join must still refuse that session.
    async with pool.acquire() as connection:
        await connection.execute(
            f'INSERT INTO "{schema}".customer_central_session_revocations '
            '(central_sid) VALUES ($1)', sid)
        still_active = await connection.fetchval(
            f'SELECT revoked_at FROM "{schema}".customer_sessions WHERE central_sid=$1',
            sid)
        assert still_active is None
    response = await get_loans(grant.session_token)
    assert response.status_code == 401
    assert stub.calls == [(str(TENANT), str(BORROWER))]
    with pytest.raises(Exception):
        await sessions.issue(claims=claims(sid=sid), tenant_id=TENANT)


@pytest.mark.asyncio
async def test_database_link_revocation_blocks_existing_cookie(environment):
    links, sessions, stub, _, _ = environment
    grant = await issue(links, sessions, sid=uuid4())
    assert (await get_loans(grant.session_token)).status_code == 200
    assert await links.revoke_self(
        issuer=ISSUER, subject=SUBJECT, tenant_id=TENANT,
        reason="Controlled integration test customer unlink",
    )
    response = await get_loans(grant.session_token)
    assert response.status_code == 401
    assert stub.calls == [(str(TENANT), str(BORROWER))]


@pytest.mark.asyncio
async def test_session_cookie_cannot_read_other_tenant_or_without_same_origin(environment):
    links, sessions, stub, _, _ = environment
    grant = await issue(links, sessions, sid=uuid4())
    assert (await get_loans(grant.session_token, headers={
        "Sec-Fetch-Site": "cross-site",
    })).status_code == 403
    assert stub.calls == []
    config = app.state.session_loan_read_config
    app.state.session_loan_read_config = SessionLoanReadConfig(
        sessions=config.sessions,
        service=LoanReadService(
            tenant_id=str(uuid4()),
            directory=NoCustomersDirectory(),
            adapter=stub,
        ),
        public_origin=ORIGIN,
    )
    assert (await get_loans(grant.session_token)).status_code == 403
    assert stub.calls == []


@pytest.mark.asyncio
async def test_invalid_upstream_result_does_not_fabricate_balance(environment):
    links, sessions, stub, _, _ = environment
    grant = await issue(links, sessions, sid=uuid4())
    stub.fail = True
    response = await get_loans(grant.session_token)
    assert response.status_code == 503
    assert response.json() == {"code": "LOAN_SERVICE_UNAVAILABLE"}
    assert "fake-upstream-sensitive-error" not in response.text
    assert "580005" not in response.text
