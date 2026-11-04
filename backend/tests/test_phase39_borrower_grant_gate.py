"""Contract tests only; no live LoanHub token or verification service."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from backend.app.borrower_credential_gate import (
    GuardedBorrowerTokenSource, VerifiedBorrowerGrant,
)
from backend.app.loanhub_adapter import LoanHubBorrowerReadAdapter, LoanHubReadError

TENANT = "d921126e-e1a7-482e-ad1b-6e99b1682e19"
BORROWER = "cb6700f8-1808-46ca-bfc2-f030ad0e2d7c"
OTHER_TENANT = "9ff995dc-ad87-4a91-8a8f-18ddfc85d991"
OTHER_BORROWER = "9ff995dc-ad87-4a91-8a8f-18ddfc85d992"
LOAN = "72de5a5b-ad44-4eea-b871-81479fe7b045"


def grant(**changes):
    now = datetime.now(timezone.utc)
    data = dict(
        token="broker-reviewed-borrower-access-token",
        tenant_id=TENANT, borrower_id=BORROWER,
        role="borrower", expires_at=now + timedelta(seconds=90),
        checked_at=now, identity_verified=True, session_active=True,
    )
    data.update(changes)
    return VerifiedBorrowerGrant(**data)


@pytest.mark.parametrize("changes", [
    dict(role="superadmin"),
    dict(role="company_admin"),
    dict(role=""),
    dict(tenant_id=OTHER_TENANT),
    dict(borrower_id=OTHER_BORROWER),
    dict(identity_verified=False),
    dict(session_active=False),
    dict(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)),
    dict(expires_at=datetime.now(timezone.utc) + timedelta(milliseconds=1)),
    dict(checked_at=datetime.now(timezone.utc) - timedelta(minutes=5)),
    dict(checked_at=datetime.now(timezone.utc) + timedelta(minutes=5)),
    dict(token=""),
    dict(token="bad token with whitespace"),
    dict(expires_at=datetime.now()),
    dict(checked_at=datetime.now()),
])
def test_invalid_or_unverified_borrower_grants_never_release_token(changes):
    source = GuardedBorrowerTokenSource(lambda *_: grant(**changes))
    assert source(TENANT, BORROWER) is None


def test_fresh_borrower_grant_uses_exact_server_supplied_identities():
    calls = []
    source = GuardedBorrowerTokenSource(
        lambda tenant, borrower: calls.append((tenant, borrower)) or grant())
    assert source(TENANT, BORROWER) == "broker-reviewed-borrower-access-token"
    assert calls == [(TENANT, BORROWER)]
    assert source("not-a-uuid", BORROWER) is None
    assert calls == [(TENANT, BORROWER)]


def test_each_read_rechecks_broker_and_revocation_not_cached():
    state = {"active": True, "calls": 0}

    def broker(_tenant, _borrower):
        state["calls"] += 1
        return grant(session_active=state["active"])

    source = GuardedBorrowerTokenSource(broker)
    assert source(TENANT, BORROWER) is not None
    state["active"] = False
    assert source(TENANT, BORROWER) is None
    assert state["calls"] == 2


@pytest.mark.asyncio
async def test_revoked_and_admin_grants_never_reach_loanhub_api():
    state = {"grant": grant()}
    outgoing = []

    def handle(request):
        outgoing.append(request)
        return httpx.Response(200, json=[{
            "id": LOAN, "company_id": TENANT,
            "borrower_id": BORROWER, "status": "active", "balance": "100.00",
        }])

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    adapter = LoanHubBorrowerReadAdapter(
        base_url="https://loanhub.example.test",
        borrower_token_for=GuardedBorrowerTokenSource(
            lambda _tenant, _borrower: state["grant"]),
        client=client,
    )
    try:
        result = await adapter.list_customer_loans(
            tenant_id=TENANT, customer_id=BORROWER)
        assert result[0].outstanding.minor_units == 10000
        assert len(outgoing) == 1
        state["grant"] = grant(session_active=False)
        with pytest.raises(LoanHubReadError):
            await adapter.list_customer_loans(
                tenant_id=TENANT, customer_id=BORROWER)
        state["grant"] = grant(role="superadmin")
        with pytest.raises(LoanHubReadError):
            await adapter.list_customer_loans(
                tenant_id=TENANT, customer_id=BORROWER)
        state["grant"] = grant(borrower_id=OTHER_BORROWER)
        with pytest.raises(LoanHubReadError):
            await adapter.list_customer_loans(
                tenant_id=TENANT, customer_id=BORROWER)
    finally:
        await client.aclose()
    assert len(outgoing) == 1


@pytest.mark.asyncio
async def test_broker_unavailable_fails_closed_before_network_call():
    outgoing = []

    def broken_broker(_tenant, _borrower):
        raise RuntimeError("internal-credential-provider-secret")

    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda req: outgoing.append(req) or httpx.Response(200, json=[])))
    adapter = LoanHubBorrowerReadAdapter(
        base_url="https://loanhub.example.test",
        borrower_token_for=GuardedBorrowerTokenSource(broken_broker),
        client=client)
    try:
        with pytest.raises(LoanHubReadError) as result:
            await adapter.list_customer_loans(
                tenant_id=TENANT, customer_id=BORROWER)
        assert "internal-credential-provider-secret" not in str(result.value)
    finally:
        await client.aclose()
    assert outgoing == []


def test_guard_accepts_only_short_recency_and_is_not_a_broker():
    with pytest.raises(ValueError):
        GuardedBorrowerTokenSource(lambda *_: None,
                                   max_check_age=timedelta(minutes=2))
    assert GuardedBorrowerTokenSource(lambda *_: None)(TENANT, BORROWER) is None
