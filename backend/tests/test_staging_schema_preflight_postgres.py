"""Read-only schema readiness checks against disposable PostgreSQL."""
import os
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio

from backend.app.staging_schema_preflight import inspect_staging_schema

URL = os.getenv("BATLOKOA_LINK_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Disposable PostgreSQL is not configured")


@pytest_asyncio.fixture
async def database():
    schema = "test_ready_" + uuid4().hex[:16]
    conn = await asyncpg.connect(URL)
    await conn.execute(f'CREATE SCHEMA "{schema}"')
    pool = await asyncpg.create_pool(URL, min_size=1, max_size=3)
    try:
        yield conn, pool, schema
    finally:
        await pool.close()
        await conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await conn.close()


@pytest.mark.asyncio
async def test_unmigrated_database_is_rejected(database):
    _, pool, schema = database
    report = await inspect_staging_schema(pool, schema=schema)
    assert not report.ready
    assert "customer_sessions" in report.missing_relations
    assert "oidc_login_transactions" in report.missing_relations


@pytest.mark.asyncio
async def test_all_three_migrations_satisfy_schema_readiness(database):
    connection, pool, schema = database
    for name in (
        "001_customer_account_links.sql",
        "002_customer_sessions.sql",
        "003_oidc_login_transactions.sql",
    ):
        sql = Path("backend/migrations", name).read_text()
        await connection.execute(sql.replace('"public".', f'"{schema}".'))
    report = await inspect_staging_schema(pool, schema=schema)
    assert report.ready, report
    assert report.missing_relations == ()
    assert report.missing_constraints == ()


@pytest.mark.asyncio
async def test_missing_unique_account_identity_constraint_blocks_readiness(database):
    connection, pool, schema = database
    for name in (
        "001_customer_account_links.sql",
        "002_customer_sessions.sql",
        "003_oidc_login_transactions.sql",
    ):
        sql = Path("backend/migrations", name).read_text()
        await connection.execute(sql.replace('"public".', f'"{schema}".'))
    await connection.execute(
        f'ALTER TABLE "{schema}".customer_account_links '
        'DROP CONSTRAINT uq_batlokoa_tenant_borrower'
    )
    report = await inspect_staging_schema(pool, schema=schema)
    assert not report.ready
    assert "customer_account_links.uq_batlokoa_tenant_borrower" in report.missing_constraints


def test_rejects_unsafe_schema_name():
    with pytest.raises(ValueError):
        import asyncio
        asyncio.run(inspect_staging_schema(None, schema="public;DROP TABLE users"))
