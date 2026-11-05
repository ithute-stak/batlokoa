"""Phase 48: isolated real-adapter proof from LoanHub to Batlokoa loan reads.

This is a network-free, synthetic JWT and synthetic loan suite. The public
Batlokoa gateway is NEVER bootstrapped or reconfigured by these tests.
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
from backend.app.loanhub_remote_borrower_context import LoanHubRemoteBorrowerContext

ORIGIN = "https://controlled-loanhub.invalid"
USER = "72de5a5b-ad44-4eea-b871-81479fe7b045"
TENANT = "d921126e-e1a7-482e-ad1b-6e99b1682e19"
OTHER_TENANT = "9ff995dc-ad87-4a91-8a8f-18ddfc85d991"
BORROWER = "cb6700f8-1808-46ca-bfc2-f030ad0e2d7c"
OTHER_BORROWER = "9ff995dc-ad87-4a91-8a8f-18ddfc85d992"
LOAN = "9ff995dc-ad87-4a91-8a8f-18ddfc85d993"


@dataclass
class LoanHubFixture:
    key: object
    revoked: bool = False
    active: bool = True
    verified: bool = True
    role: str = "borrower"
    context_tenant: str = TENANT
    context_borrower: str = BORROWER
    context_status: int = 200
    loans_status: int = 200
    loan_tenant: str = TENANT
    loan_borrower: str = BORROWER
    calls: list[str] = field(default_factory=list)

    def token(self, *, minutes: int = 5):
        return jwt.encode({
            "user_id": USER, "token_type": "access",
            "session_version": 1, "session_jti": str(uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes),
        }, self.key, algorithm="RS256")

    def handle(self, request: httpx.Request) -> httpx.Response:
        assert request.url.host == "controlled-loanhub.invalid"
        assert request.url.scheme == "https"
        assert request.method == "GET"
        assert "x-company-id" not in request.headers
        assert "x-active-role" not in request.headers
        assert request.headers["cache-control"] == "no-store"
        self.calls.append(request.url.path)
        if self.revoked:
            return httpx.Response(401)
        if request.url.path == "/api/v1/auth/me":
            return httpx.Response(200, json={
                "id": USER, "role": self.role, "is_active": self.active,
                "is_verified": self.verified, "must_change_password": False,
            })
        if request.url.path == "/api/v1/auth/borrower-context":
            assert request.url.params.get("company_id") == TENANT
            return httpx.Response(self.context_status, json={
                "user_id": USER, "company_id": self.context_tenant,
                "borrower_id": self.context_borrower, "role": self.role,
                "session_active": not self.revoked,
                "account_active": self.active,
            })
        if request.url.path == "/api/v1/loans/":
            return httpx.Response(self.loans_status, json=[{
                "id": LOAN, "company_id": self.loan_tenant,
                "borrower_id": self.loan_borrower,
                "balance": "125.70", "status": "active",
            }])
        raise AssertionError("Unexpected upstream HTTP request")


@pytest.fixture
def stack():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    upstream = LoanHubFixture(key)
    client = httpx.Client(transport=httpx.MockTransport(upstream.handle))
    async_client = httpx.AsyncClient(transport=httpx.MockTransport(upstream.handle))
    current = {"token": upstream.token()}
    context = LoanHubRemoteBorrowerContext(base_url=ORIGIN, client=client)
    identity = LoanHubIdentityVerifier(
        base_url=ORIGIN, public_key=key.public_key(),
        resolve_remote_borrower_context=context, client=client,
    )
    broker = LoanHubBorrowerGrantBroker(
        token_for=lambda _tenant, _borrower: current["token"],
        verify_token_for=identity,
    )
    loans = LoanHubBorrowerReadAdapter(
        base_url=ORIGIN, borrower_token_for=GuardedBorrowerTokenSource(broker),
        client=async_client,
    )
    yield upstream, current, loans
    client.close()


async def borrow(loans, tenant=TENANT, borrower=BORROWER):
    return await loans.list_customer_loans(tenant_id=tenant, customer_id=borrower)


@pytest.mark.asyncio
async def test_real_remote_proof_allows_exact_borrower_and_no_extra_apis(stack):
    up, tokens, loans = stack
    try:
        result = await borrow(loans)
        assert len(result) == 1
        assert result[0].loan_id == LOAN
        assert result[0].outstanding.minor_units == 12570
        assert up.calls == [
            "/api/v1/auth/me",
            "/api/v1/auth/borrower-context",
            "/api/v1/loans/",
        ]
    finally:
        await loans._client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("revoked", True),
    ("role", "superadmin"),
    ("active", False),
    ("verified", False),
    ("context_tenant", OTHER_TENANT),
    ("context_borrower", OTHER_BORROWER),
    ("context_status", 401),
    ("context_status", 503),
])
async def test_remote_denials_stop_before_any_loan_request(stack, field, value):
    up, tokens, loans = stack
    try:
        assert (await borrow(loans))[0].outstanding.minor_units == 12570
        up.calls.clear()
        setattr(up, field, value)
        with pytest.raises(LoanHubReadError):
            await borrow(loans)
        assert "/api/v1/loans/" not in up.calls
    finally:
        await loans._client.aclose()


@pytest.mark.asyncio
async def test_session_rotation_and_expired_grant_fail_closed(stack):
    up, tokens, loans = stack
    try:
        assert (await borrow(loans))[0].outstanding.minor_units == 12570
        up.calls.clear()
        tokens["token"] = up.token(minutes=-1)
        with pytest.raises(LoanHubReadError):
            await borrow(loans)
        assert up.calls == []
        tokens["token"] = up.token()
        up.revoked = True
        with pytest.raises(LoanHubReadError):
            await borrow(loans)
        assert "/api/v1/loans/" not in up.calls
    finally:
        await loans._client.aclose()


@pytest.mark.asyncio
async def test_loan_response_cross_tenant_and_borrower_do_not_leak(stack):
    up, tokens, loans = stack
    try:
        up.loan_tenant = OTHER_TENANT
        with pytest.raises(LoanHubReadError):
            await borrow(loans)
        up.loan_tenant = TENANT
        up.loan_borrower = OTHER_BORROWER
        with pytest.raises(LoanHubReadError):
            await borrow(loans)
    finally:
        await loans._client.aclose()


@pytest.mark.asyncio
async def test_caller_cannot_switch_company_or_borrower(stack):
    up, tokens, loans = stack
    try:
        with pytest.raises(LoanHubReadError):
            await borrow(loans, OTHER_TENANT, BORROWER)
        with pytest.raises(LoanHubReadError):
            await borrow(loans, TENANT, OTHER_BORROWER)
        assert "/api/v1/loans/" not in up.calls
    finally:
        await loans._client.aclose()
