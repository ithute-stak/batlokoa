"""Real disposable PostgreSQL transaction tests, including callback races."""
import asyncio
import os
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet

from backend.app.oidc_login import PendingLogin
from backend.app.oidc_transaction_store import PostgresOidcTransactionStore

URL = os.getenv("BATLOKOA_LINK_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Disposable PostgreSQL URL absent")


@pytest_asyncio.fixture
async def fixture_db():
    schema = "test_oidc_" + uuid4().hex[:14]
    conn = await asyncpg.connect(URL)
    await conn.execute(f'CREATE SCHEMA "{schema}"')
    try:
        sql = Path("backend/migrations/003_oidc_login_transactions.sql").read_text()
        await conn.execute(sql.replace('"public".', f'"{schema}".'))
        pool = await asyncpg.create_pool(URL, min_size=1, max_size=5)
        try:
            yield PostgresOidcTransactionStore(
                pool, encryption_key=Fernet.generate_key(), schema=schema
            ), pool, schema
        finally:
            await pool.close()
    finally:
        await conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await conn.close()


def pending():
    return PendingLogin(
        state="safe-state-" + "s" * 44,
        nonce="safe-nonce-" + "n" * 44,
        code_verifier="safe-verifier-" + "v" * 54,
    )


@pytest.mark.asyncio
async def test_encrypted_state_and_atomic_one_use(fixture_db):
    store, pool, schema = fixture_db
    item = pending()
    await store.save(item, expires_seconds=300)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f'SELECT state_sha256, encrypted_payload FROM "{schema}".oidc_login_transactions'
        )
    assert row["state_sha256"] != item.state
    assert item.nonce.encode() not in row["encrypted_payload"]
    assert item.code_verifier.encode() not in row["encrypted_payload"]
    assert await store.consume(state=item.state) == item
    assert await store.consume(state=item.state) is None


@pytest.mark.asyncio
async def test_racing_callbacks_consumed_exactly_once(fixture_db):
    store, _, _ = fixture_db
    item = pending()
    await store.save(item, expires_seconds=300)
    results = await asyncio.gather(*(
        store.consume(state=item.state) for _ in range(12)
    ))
    assert results.count(item) == 1
    assert results.count(None) == 11


@pytest.mark.asyncio
async def test_expired_state_is_deleted_without_returning_secrets(fixture_db):
    store, pool, schema = fixture_db
    item = pending()
    await store.save(item, expires_seconds=30)
    async with pool.acquire() as conn:
        await conn.execute(
            f'UPDATE "{schema}".oidc_login_transactions SET '
            "expires_at=now()-interval '1 minute', "
            "created_at=now()-interval '2 minutes'"
        )
    assert await store.consume(state=item.state) is None
    async with pool.acquire() as conn:
        assert await conn.fetchval(
            f'SELECT count(*) FROM "{schema}".oidc_login_transactions'
        ) == 0


@pytest.mark.asyncio
async def test_wrong_key_fails_closed_and_still_consumes(fixture_db):
    store, pool, schema = fixture_db
    item = pending()
    await store.save(item, expires_seconds=300)
    other = PostgresOidcTransactionStore(
        pool, encryption_key=Fernet.generate_key(), schema=schema
    )
    assert await other.consume(state=item.state) is None
    assert await store.consume(state=item.state) is None


@pytest.mark.asyncio
async def test_duplicate_state_is_blocked_by_database(fixture_db):
    store, _, _ = fixture_db
    item = pending()
    await store.save(item, expires_seconds=300)
    with pytest.raises(asyncpg.UniqueViolationError):
        await store.save(item, expires_seconds=300)


def test_invalid_schema_and_key_fail_closed():
    with pytest.raises(ValueError):
        PostgresOidcTransactionStore(None, encryption_key=Fernet.generate_key(),
                                     schema="public;DROP")
    with pytest.raises(ValueError):
        PostgresOidcTransactionStore(None, encryption_key=b"bad", schema="public")
