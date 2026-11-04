"""Phase 44: controlled in-process LoanHub HTTP integration harness.

The fake LoanHub transport is explicit, deterministic and network-free.
It simulates LoanHub's authenticated /auth/me and borrower-filtered /loans/
contracts, while invoking the real Batlokoa verifier, broker, guarded token
supplier and read-only LoanHub HTTP adapter. There is no production bootstrap.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.app.borrower_credential_gate import GuardedBorrowerTokenSource
from backend.app.loanhub_adapter import LoanHubBorrowerReadAdapter, LoanHubReadError
from backend.app.loanhub_grant_broker import LoanHubBorrowerGrantBroker
from backend.app.loanhub_identity_verifier import LoanHubIdentityVerifier

ORIGIN = "https://controlled-loanhub.invalid"
TENANT = "d921126e-e1a7-482e-ad1b-6e99b1682e19"
OTHER_TENANT = "9ff995dc-ad87-4a91-8a8f-18ddfc85d991"
BORROWER = "cb6700f8-1808-46ca-bfc2-f030ad0e2d7c"
OTHER_BORROWER = "9ff995dc-ad87-4a91-8a8f-18ddfc85d992"
USER = "72de5a5b-ad44-4eea-b871-81479fe7b045"
LOAN_ID = "9ff995dc-ad87-4a91-8a8f-18ddfc85d993"


@dataclass
class ControlledLoanHub:
    signing_key: object
    active: bool = True
    role: str = "borrower"
    verified: bool = True
    revoked: bool = False
    mapping: tuple[str, str] | None = (TENANT, BORROWER)
    loans_online: bool = True
    auth_online: bool = True
    loan_tenant: str = TENANT
    loan_borrower: str = BORROWER
    recorded: list[tuple[str, str]] = field(default_factory=list)

    def token(self, *, expired=False, user=USER) -> str:
        return jwt.encode({
            "user_id": user, "token_type": "access",
            "session_version": 1, "session_jti": str(uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(
                minutes=-1 if expired else 5),
        }, self.signing_key, algorithm="RS256")

    def handler(self, request: httpx.Request) -> httpx.Response:
        # This is the ONLY allowed network surface for these tests.
        assert request.url.scheme == "https"
        assert request.url.host == "controlled-loanhub.invalid"
        assert request.method == "GET"
        assert "x-company-id" not in request.headers
        assert "x-active-role" not in request.headers
        assert request.headers["cache-control"] == "no-store"
        self.recorded.append((request.method, request.url.path))
        bearer = request.headers.get("authorization", "")
        if not bearer.startswith("Bearer "):
            return httpx.Response(401)
        if request.url.path == "/api/v1/auth/me":
            if not self.auth_online:
                return httpx.Response(503)
            if self.revoked:
                return httpx.Response(401)
            return httpx.Response(200, json={
                "id": USER, "role": self.role,
                "is_active": self.active, "is_verified": self.verified,
                "must_change_password": False,
            })
        if request.url.path == "/api/v1/loans/":
            if not self.loans_online:
                return httpx.Response(503)
            if self.revoked or self.role != "borrower" or not self.active:
                return httpx.Response(403)
            return httpx.Response(200, json=[{
                "id": LOAN_ID,
                "company_id": self.loan_tenant,
                "borrower_id": self.loan_borrower,
                "balance": "125.70",
                "status": "active",
            }])
        # The fixture will fail if any extra upstream endpoint is used.
        raise AssertionError("Unexpected LoanHub endpoint")


@pytest.fixture
def controlled():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    upstream = ControlledLoanHub(signing_key=key)
    sync_client = httpx.Client(transport=httpx.MockTransport(upstream.handler))
    async_client = httpx.AsyncClient(transport=httpx.MockTransport(upstream.handler))
    current = {"token": upstream.token()}

    def mapping(user_id):
        return upstream.mapping if user_id == USER else None

    verifier = LoanHubIdentityVerifier(
        base_url=ORIGIN, public_key=key.public_key(),
        resolve_borrower_mapping=mapping,
        client=sync_client,
    )
    broker = LoanHubBorrowerGrantBroker(
        token_for=lambda tenant, borrower: current["token"],
        verify_token_for=verifier,
    )
    adapter = LoanHubBorrowerReadAdapter(
        base_url=ORIGIN,
        borrower_token_for=GuardedBorrowerTokenSource(broker),
        client=async_client,
    )
    yield upstream, current, adapter
    sync_client.close()
    # Cleanup of async client occurs in test via fixture helper below.
    # No real network sockets are opened with MockTransport.


async def read(adapter, *, tenant=TENANT, borrower=BORROWER):
    return await adapter.list_customer_loans(tenant_id=tenant, customer_id=borrower)


@pytest.mark.asyncio
async def test_exact_read_only_contract_and_successful_authorized_borrower(controlled):
    upstream, current, adapter = controlled
    result = await read(adapter)
    assert len(result) == 1
    assert result[0].loan_id == LOAN_ID
    assert result[0].outstanding.minor_units == 12570
    assert upstream.recorded == [
        ("GET", "/api/v1/auth/me"), ("GET", "/api/v1/loans/")
    ]
    await adapter._client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    ("revoked", True),
    ("active", False),
    ("verified", False),
    ("role", "superadmin"),
    ("role", "company_admin"),
    ("mapping", (OTHER_TENANT, BORROWER)),
    ("mapping", (TENANT, OTHER_BORROWER)),
    ("mapping", None),
    ("auth_online", False),
])
async def test_upstream_revocation_isolation_and_auth_failures_block_loan_http(controlled, change):
    upstream, current, adapter = controlled
    assert (await read(adapter))[0].outstanding.minor_units == 12570
    setattr(upstream, *change)
    before = sum(path == "/api/v1/loans/" for _, path in upstream.recorded)
    with pytest.raises(LoanHubReadError):
        await read(adapter)
    after = sum(path == "/api/v1/loans/" for _, path in upstream.recorded)
    assert before == after == 1
    await adapter._client.aclose()


@pytest.mark.asyncio
async def test_expired_token_and_foreign_identity_never_call_upstream(controlled):
    upstream, current, adapter = controlled
    current["token"] = upstream.token(expired=True)
    with pytest.raises(LoanHubReadError):
        await read(adapter)
    assert upstream.recorded == []
    current["token"] = upstream.token(user=str(uuid4()))
    with pytest.raises(LoanHubReadError):
        await read(adapter)
    assert upstream.recorded == [("GET", "/api/v1/auth/me")]
    await adapter._client.aclose()


@pytest.mark.asyncio
async def test_wrong_tenant_or_borrower_response_never_reaches_customer(controlled):
    upstream, current, adapter = controlled
    upstream.loan_tenant = OTHER_TENANT
    with pytest.raises(LoanHubReadError, match="another tenant"):
        await read(adapter)
    upstream.loan_tenant = TENANT
    upstream.loan_borrower = OTHER_BORROWER
    with pytest.raises(LoanHubReadError, match="another tenant or borrower"):
        await read(adapter)
    await adapter._client.aclose()


@pytest.mark.asyncio
async def test_borrower_mapping_change_and_loanhub_outage_do_not_return_stale_balance(controlled):
    upstream, current, adapter = controlled
    assert (await read(adapter))[0].outstanding.minor_units == 12570
    upstream.mapping = None
    with pytest.raises(LoanHubReadError):
        await read(adapter)
    upstream.mapping = (TENANT, BORROWER)
    upstream.loans_online = False
    with pytest.raises(LoanHubReadError):
        await read(adapter)
    await adapter._client.aclose()


@pytest.mark.asyncio
async def test_no_service_token_or_caller_chosen_tenant_can_bypass_verifier(controlled):
    upstream, current, adapter = controlled
    with pytest.raises(LoanHubReadError):
        await read(adapter, tenant=OTHER_TENANT)
    with pytest.raises(LoanHubReadError):
        await read(adapter, borrower=OTHER_BORROWER)
    assert all(path != "/api/v1/loans/" for _, path in upstream.recorded)
    await adapter._client.aclose()
