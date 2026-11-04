"""Phase 37: revoked central sessions must never resolve to borrowers.

The fake pool models the revocation membership predicate; no real DB secrets.
"""
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from backend.app.sessions import PostgresSessionStore


class Connection:
    def __init__(self, *, central_revoked=False):
        self.central_revoked = central_revoked
        self.sql = []
        self.sid = uuid4()

    async def fetchrow(self, sql, *params):
        self.sql.append(sql)
        assert len(params) == 1
        assert "token_sha256=$1" in sql
        # The DB-layer revocation constraint must be enforced by SQL, not by
        # an application-level stale session cache.
        assert 'NOT EXISTS' in sql
        assert '"public".customer_central_session_revocations' in sql
        assert 'r.central_sid=s.central_sid' in sql
        if self.central_revoked:
            return None
        return {
            "issuer": "https://auth.example.test",
            "subject": "verified-subject",
            "tenant_id": uuid4(),
            "borrower_id": uuid4(),
            "central_sid": self.sid,
            "csrf_sha256": "unused",
        }


class Pool:
    def __init__(self, connection):
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


@pytest.mark.asyncio
async def test_resolve_checks_central_revocation_on_each_database_read():
    connection = Connection()
    store = PostgresSessionStore(Pool(connection))
    token = "safe-opaque-session-token-long-enough-for-test"
    first = await store.resolve(token)
    assert first is not None
    assert first.central_sid == connection.sid

    # Simulate authenticated central revocation between two reads:
    # even if a stale customer session row remains unmarked, revocation
    # membership must prevent the second resolution.
    connection.central_revoked = True
    assert await store.resolve(token) is None
    assert len(connection.sql) == 2


@pytest.mark.asyncio
async def test_invalid_session_never_queries_database():
    connection = Connection()
    store = PostgresSessionStore(Pool(connection))
    assert await store.resolve("short") is None
    assert await store.resolve("invalid\u00e9" * 12) is None
    assert connection.sql == []
