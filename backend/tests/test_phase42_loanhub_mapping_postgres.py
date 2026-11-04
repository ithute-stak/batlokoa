"""Disposable PostgreSQL tests for real SQL-backed LoanHub tenant ownership.

These are minimal compatibility tables matching relevant LoanHub columns,
not the real production database; only test IDs and SELECT-only operations.
"""
import os
from uuid import uuid4

import psycopg
import pytest

from backend.app.loanhub_borrower_mapping import LoanHubBorrowerMappingResolver

URL = os.getenv("BATLOKOA_LINK_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Disposable PostgreSQL URL absent")


@pytest.fixture
def mapped_db():
    schema = "test_lhmap_" + uuid4().hex[:14]
    user, borrower, tenant, other_tenant = (uuid4() for _ in range(4))
    with psycopg.connect(URL) as admin:
        admin.execute(f'CREATE SCHEMA "{schema}"')
        admin.execute(f"""
            CREATE TABLE "{schema}".users (
                id uuid PRIMARY KEY, role text NOT NULL,
                is_active boolean NOT NULL, is_verified boolean NOT NULL
            );
            CREATE TABLE "{schema}".borrowers (
                id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES "{schema}".users(id)
            );
            CREATE TABLE "{schema}".loan_companies (
                id uuid PRIMARY KEY, is_active boolean NOT NULL
            );
            CREATE TABLE "{schema}".client_company_loan (
                id uuid PRIMARY KEY,
                company_id uuid NOT NULL REFERENCES "{schema}".loan_companies(id),
                borrower_id uuid NOT NULL REFERENCES "{schema}".borrowers(id)
            );
        """)
        admin.execute(f'INSERT INTO "{schema}".users VALUES (%s, %s, TRUE, TRUE)',
                      (user, "BORROWER"))
        admin.execute(f'INSERT INTO "{schema}".borrowers VALUES (%s, %s)',
                      (borrower, user))
        admin.execute(f'INSERT INTO "{schema}".loan_companies VALUES (%s, TRUE), (%s, TRUE)',
                      (tenant, other_tenant))
        admin.execute(f'INSERT INTO "{schema}".client_company_loan VALUES (%s, %s, %s)',
                      (uuid4(), tenant, borrower))
    # Fresh connections use server-side search_path; no SQL is executed
    # before the resolver's transaction READ ONLY statement.
    def connect():
        return psycopg.connect(
            URL, options=f"-csearch_path={schema}", connect_timeout=3)

    resolver = LoanHubBorrowerMappingResolver(
        tenant_id=str(tenant), connect=connect)
    try:
        yield resolver, schema, user, borrower, tenant, other_tenant
    finally:
        with psycopg.connect(URL, autocommit=True) as admin:
            admin.execute(f'DROP SCHEMA "{schema}" CASCADE')


def modify(schema, sql, params=()):
    with psycopg.connect(URL) as conn:
        conn.execute(sql.format(schema=schema), params)


def test_verified_user_and_approved_loan_company_resolve(mapped_db):
    resolver, schema, user, borrower, tenant, _ = mapped_db
    assert resolver(str(user)) == (str(tenant), str(borrower))
    assert resolver(str(uuid4())) is None
    assert resolver("malformed-user") is None


def test_unrelated_company_cannot_use_existing_borrower_loan(mapped_db):
    resolver, schema, user, borrower, tenant, other_tenant = mapped_db
    other = LoanHubBorrowerMappingResolver(
        tenant_id=str(other_tenant), connect=resolver._connect)
    assert other(str(user)) is None
    modify(schema,
           'INSERT INTO "{schema}".client_company_loan VALUES (%s, %s, %s)',
           (uuid4(), other_tenant, borrower))
    # A tenant is considered related only after its own loan association.
    assert other(str(user)) == (str(other_tenant), str(borrower))


@pytest.mark.parametrize("sql", [
    'UPDATE "{schema}".users SET role=\'SUPERADMIN\'',
    'UPDATE "{schema}".users SET is_active=FALSE',
    'UPDATE "{schema}".users SET is_verified=FALSE',
    'UPDATE "{schema}".loan_companies SET is_active=FALSE',
    'DELETE FROM "{schema}".client_company_loan',
])
def test_role_status_unlink_and_loan_removal_revoke_mapping(mapped_db, sql):
    resolver, schema, user, borrower, tenant, _ = mapped_db
    assert resolver(str(user)) is not None
    modify(schema, sql)
    assert resolver(str(user)) is None


def test_read_only_transaction_blocks_mutating_connection_hooks(mapped_db):
    resolver, schema, user, borrower, tenant, _ = mapped_db

    class MutatingConnection:
        def __enter__(self):
            self.connection = resolver._connect()
            self.connection.__enter__()
            return self

        def __exit__(self, *args):
            return self.connection.__exit__(*args)

        def execute(self, sql, params=None):
            if sql == "SET TRANSACTION READ ONLY":
                return self.connection.execute(sql)
            # A malicious/wrong connection policy cannot mutate data because
            # the resolver started a read-only transaction.
            with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
                self.connection.execute(
                    f'DELETE FROM "{schema}".client_company_loan')
            raise psycopg.errors.ReadOnlySqlTransaction("blocked")

    unsafe = LoanHubBorrowerMappingResolver(
        tenant_id=str(tenant), connect=lambda: MutatingConnection())
    assert unsafe(str(user)) is None
    assert resolver(str(user)) == (str(tenant), str(borrower))


def test_invalid_approved_tenant_and_unavailable_db_denied(mapped_db):
    resolver, _, user, _, _, _ = mapped_db
    with pytest.raises(ValueError):
        LoanHubBorrowerMappingResolver(
            tenant_id="untrusted-name", connect=resolver._connect)

    def unavailable():
        raise psycopg.OperationalError("database unavailable")

    blocked = LoanHubBorrowerMappingResolver(
        tenant_id=str(uuid4()), connect=unavailable)
    assert blocked(str(user)) is None


@pytest.mark.asyncio
async def test_full_mocked_token_to_borrower_loan_chain_revokes_after_unlink(mapped_db):
    """Signed token -> /auth/me -> real PG mapping -> broker -> GET /loans."""
    from datetime import datetime, timedelta, timezone
    import httpx
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    from backend.app.borrower_credential_gate import GuardedBorrowerTokenSource
    from backend.app.loanhub_grant_broker import LoanHubBorrowerGrantBroker
    from backend.app.loanhub_identity_verifier import LoanHubIdentityVerifier
    from backend.app.loanhub_adapter import LoanHubBorrowerReadAdapter, LoanHubReadError

    mapping, schema, user, borrower, tenant, _ = mapped_db
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = jwt.encode({
        "user_id": str(user), "token_type": "access",
        "session_jti": str(uuid4()), "session_version": 1,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }, private, algorithm="RS256")
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/api/v1/auth/me":
            return httpx.Response(200, json={
                "id": str(user), "role": "borrower",
                "is_active": True, "is_verified": True,
                "must_change_password": False,
            })
        if request.url.path == "/api/v1/loans/":
            return httpx.Response(200, json=[{
                "id": str(uuid4()), "company_id": str(tenant),
                "borrower_id": str(borrower),
                "balance": "51.25", "status": "active",
            }])
        return httpx.Response(404)

    sync_client = httpx.Client(transport=httpx.MockTransport(handler))
    async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        verifier = LoanHubIdentityVerifier(
            base_url="https://loanhub.example.test",
            public_key=private.public_key(),
            resolve_borrower_mapping=mapping,
            client=sync_client,
        )
        vault = lambda tenant_id, borrower_id: token
        grant_source = GuardedBorrowerTokenSource(LoanHubBorrowerGrantBroker(
            token_for=vault, verify_token_for=verifier,
        ))
        adapter = LoanHubBorrowerReadAdapter(
            base_url="https://loanhub.example.test",
            borrower_token_for=grant_source,
            client=async_client,
        )
        results = await adapter.list_customer_loans(
            tenant_id=str(tenant), customer_id=str(borrower))
        assert results[0].outstanding.minor_units == 5125
        assert [req.url.path for req in requests] == [
            "/api/v1/auth/me", "/api/v1/loans/",
        ]
        modify(schema, 'DELETE FROM "{schema}".client_company_loan')
        with pytest.raises(LoanHubReadError):
            await adapter.list_customer_loans(
                tenant_id=str(tenant), customer_id=str(borrower))
        # Verification may reach /auth/me, but revocation blocks /loans.
        assert [req.url.path for req in requests].count("/api/v1/loans/") == 1
    finally:
        sync_client.close()
        await async_client.aclose()
