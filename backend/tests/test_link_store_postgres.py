"""Real PostgreSQL integration tests for the persistent link store.

CI uses a disposable PostgreSQL service and an isolated schema. These tests
validate actual unique indexes, transactional rollback, audit and revocation.
No real customer data, accounts, or external LoanHub service is used.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio

from backend.app.account_linking import LinkConflict, LinkDenied
from backend.app.link_store import PostgresCustomerLinkStore

URL = os.getenv("BATLOKOA_LINK_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Disposable PostgreSQL test URL not configured")
ISSUER = "https://auth.example.test"
TENANT = UUID("d921126e-e1a7-482e-ad1b-6e99b1682e19")
BORROWER = UUID("cb6700f8-1808-46ca-bfc2-f030ad0e2d7c")


@pytest_asyncio.fixture
async def db():
    schema = "test_link_" + uuid4().hex[:16]
    admin = await asyncpg.connect(URL)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    sql = Path("backend/migrations/001_customer_account_links.sql").read_text()
    try:
        await admin.execute(sql.replace('"public".', f'"{schema}".'))
        pool = await asyncpg.create_pool(URL, min_size=1, max_size=4)
        try:
            yield PostgresCustomerLinkStore(pool, schema=schema), pool, schema
        finally:
            await pool.close()
    finally:
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()


async def link(store, *, subject="subject-1", borrower=BORROWER,
               proof="proof-1", consent="consent-1", tenant=TENANT):
    return await store.bind_once(
        issuer=ISSUER, subject=subject, tenant_id=tenant, borrower_id=borrower,
        consent_reference=consent, proof_id=proof,
    )


@pytest.mark.asyncio
async def test_insert_lookup_audit_and_revocation(db):
    store, pool, schema = db
    record = await link(store)
    assert record.auth_subject == "subject-1"
    assert record.customer_id == str(BORROWER)
    assert await store.lookup(issuer=ISSUER, subject="subject-1") == record
    assert await store.lookup(issuer=ISSUER, subject="other-subject") is None
    assert await store.revoke_self(
        issuer=ISSUER, subject="subject-1", tenant_id=TENANT,
        reason="Customer requested account unlinking",
    )
    assert await store.lookup(issuer=ISSUER, subject="subject-1") is None
    assert not await store.revoke_self(
        issuer=ISSUER, subject="subject-1", tenant_id=TENANT,
        reason="Customer requested account unlinking",
    )
    async with pool.acquire() as connection:
        records = await connection.fetch(
            f'SELECT event_type FROM "{schema}".customer_account_link_events ORDER BY created_at, event_type'
        )
        assert sorted(r["event_type"] for r in records) == ["linked", "revoked"]
        row = await connection.fetchrow(
            f'SELECT proof_sha256, consent_sha256, revoked_at FROM "{schema}".customer_account_links'
        )
        assert row["proof_sha256"] != "proof-1"
        assert row["consent_sha256"] != "consent-1"
        assert row["revoked_at"] is not None


@pytest.mark.asyncio
async def test_unique_subject_borrower_proof_and_consent_enforced_by_database(db):
    store, _, _ = db
    await link(store)
    for args in (
        dict(subject="subject-1", borrower=uuid4(), proof="proof-2", consent="consent-2"),
        dict(subject="subject-2", borrower=BORROWER, proof="proof-3", consent="consent-3"),
        dict(subject="subject-3", borrower=uuid4(), proof="proof-1", consent="consent-4"),
        dict(subject="subject-4", borrower=uuid4(), proof="proof-4", consent="consent-1"),
    ):
        with pytest.raises(LinkConflict):
            await link(store, **args)


@pytest.mark.asyncio
async def test_concurrent_double_link_cannot_create_two_mapping_rows(db):
    store, pool, schema = db
    results = await asyncio.gather(
        link(store), link(store, proof="proof-2", consent="consent-2"),
        return_exceptions=True,
    )
    assert len([r for r in results if not isinstance(r, Exception)]) == 1
    assert len([r for r in results if isinstance(r, LinkConflict)]) == 1
    async with pool.acquire() as connection:
        assert await connection.fetchval(
            f'SELECT count(*) FROM "{schema}".customer_account_links'
        ) == 1
        assert await connection.fetchval(
            f'SELECT count(*) FROM "{schema}".customer_account_link_events'
        ) == 1


@pytest.mark.asyncio
async def test_failed_audit_insert_rolls_back_link(db):
    store, pool, schema = db
    async with pool.acquire() as connection:
        await connection.execute(f"""
            CREATE OR REPLACE FUNCTION "{schema}".reject_link_event()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              RAISE EXCEPTION 'audit not available';
            END;
            $$;
            CREATE TRIGGER deny_audit BEFORE INSERT
            ON "{schema}".customer_account_link_events
            FOR EACH ROW EXECUTE FUNCTION "{schema}".reject_link_event();
        """)
    with pytest.raises(asyncpg.RaiseError):
        await link(store)
    assert await store.lookup(issuer=ISSUER, subject="subject-1") is None


@pytest.mark.asyncio
async def test_revocation_is_tenant_scoped_and_reserved_identity_cannot_relink(db):
    store, pool, schema = db
    await link(store)
    assert not await store.revoke_self(
        issuer=ISSUER, subject="subject-1", tenant_id=uuid4(),
        reason="Not the mapped tenant requesting unlink",
    )
    assert await store.lookup(issuer=ISSUER, subject="subject-1") is not None
    assert await store.revoke_self(
        issuer=ISSUER, subject="subject-1", tenant_id=TENANT,
        reason="Customer requested account unlinking",
    )
    with pytest.raises(LinkConflict):
        await link(store, proof="new-proof", consent="new-consent")
    async with pool.acquire() as connection:
        assert await connection.fetchval(
            f'SELECT count(*) FROM "{schema}".customer_account_link_events'
        ) == 2


def test_schema_name_cannot_inject_sql():
    with pytest.raises(ValueError):
        PostgresCustomerLinkStore(None, schema='public;DROP TABLE customer_account_links')
