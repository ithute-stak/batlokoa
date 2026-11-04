"""Phase 40 broker tests: no live token vault, LoanHub or customer identities."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from backend.app.borrower_credential_gate import GuardedBorrowerTokenSource
from backend.app.loanhub_adapter import LoanHubBorrowerReadAdapter, LoanHubReadError
from backend.app.loanhub_grant_broker import (
    BorrowerAccountEvidence, LoanHubBorrowerGrantBroker,
)

TENANT = "d921126e-e1a7-482e-ad1b-6e99b1682e19"
BORROWER = "cb6700f8-1808-46ca-bfc2-f030ad0e2d7c"
OTHER_BORROWER = "9ff995dc-ad87-4a91-8a8f-18ddfc85d991"
OTHER_TENANT = "9ff995dc-ad87-4a91-8a8f-18ddfc85d992"
LOAN = "72de5a5b-ad44-4eea-b871-81479fe7b045"
TOKEN = "server-vault-borrower-token"


def evidence(**overrides):
    now = datetime.now(timezone.utc)
    data = dict(
        tenant_id=TENANT, borrower_id=BORROWER,
        role="borrower", account_active=True, session_active=True,
        verified_at=now, token_expires_at=now + timedelta(minutes=2),
    )
    data.update(overrides)
    return BorrowerAccountEvidence(**data)


def broker(*, record=None, token=TOKEN):
    calls = []
    if record is None:
        record = evidence()

    def vault(t, b):
        calls.append(("vault", t, b))
        return token

    def verifier(raw, t, b):
        calls.append(("verify", raw, t, b))
        return record

    return LoanHubBorrowerGrantBroker(token_for=vault, verify_token_for=verifier), calls


def test_default_vault_denial_never_contacts_verifier():
    calls = []
    source = LoanHubBorrowerGrantBroker(
        token_for=lambda t, b: None,
        verify_token_for=lambda *args: calls.append(args))
    assert source(TENANT, BORROWER) is None
    assert calls == []


@pytest.mark.parametrize("modified", [
    {"role": "superadmin"},
    {"role": "company_admin"},
    {"role": "staff"},
    {"tenant_id": OTHER_TENANT},
    {"borrower_id": OTHER_BORROWER},
    {"account_active": False},
    {"session_active": False},
    {"verified_at": datetime.now(timezone.utc) - timedelta(minutes=1)},
    {"verified_at": datetime.now(timezone.utc) + timedelta(minutes=1)},
    {"token_expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)},
    {"token_expires_at": datetime.now()},
    {"verified_at": datetime.now()},
    {"token_expires_at": datetime.now()},
])
def test_denied_identity_state_or_unverified_time_never_yields_grant(modified):
    source, _ = broker(record=evidence(**modified))
    assert source(TENANT, BORROWER) is None


def test_verified_borrower_only_returns_tenant_bound_grant():
    source, calls = broker()
    proof = source(TENANT, BORROWER)
    assert proof is not None
    assert proof.token == TOKEN
    assert proof.role == "borrower"
    assert proof.identity_verified and proof.session_active
    assert calls == [
        ("vault", TENANT, BORROWER),
        ("verify", TOKEN, TENANT, BORROWER),
    ]


def test_invalid_ids_and_broker_failure_fail_closed_without_any_grants():
    called = []
    source = LoanHubBorrowerGrantBroker(
        token_for=lambda t, b: called.append((t, b)) or TOKEN,
        verify_token_for=lambda *_: (_ for _ in ()).throw(
            RuntimeError("secret-internal-credential-error")))
    assert source("not-uuid", BORROWER) is None
    assert called == []
    assert source(TENANT, BORROWER) is None
    assert called == [(TENANT, BORROWER)]


def test_per_request_broker_rechecks_revocation_without_caching():
    status = {"active": True, "calls": 0}

    def check(token, tenant, borrower):
        status["calls"] += 1
        return evidence(session_active=status["active"])

    source = GuardedBorrowerTokenSource(LoanHubBorrowerGrantBroker(
        token_for=lambda t, b: TOKEN, verify_token_for=check))
    assert source(TENANT, BORROWER) == TOKEN
    status["active"] = False
    assert source(TENANT, BORROWER) is None
    assert status["calls"] == 2


@pytest.mark.asyncio
async def test_broker_to_read_only_loanhub_adapter_rejects_cross_customer_and_revocation():
    state = {"active": True, "role": "borrower"}
    outgoing = []

    def verifier(raw, tenant, borrower):
        return evidence(session_active=state["active"], role=state["role"])

    source = GuardedBorrowerTokenSource(LoanHubBorrowerGrantBroker(
        token_for=lambda tenant, borrower: TOKEN,
        verify_token_for=verifier,
    ))
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda req: outgoing.append(req) or httpx.Response(200, json=[{
            "id": LOAN, "company_id": TENANT, "borrower_id": BORROWER,
            "status": "active", "balance": "250.05",
        }])))
    adapter = LoanHubBorrowerReadAdapter(
        base_url="https://loanhub.example.test",
        borrower_token_for=source, client=client)
    try:
        assert (await adapter.list_customer_loans(
            tenant_id=TENANT, customer_id=BORROWER)
        )[0].outstanding.minor_units == 25005
        assert outgoing[0].method == "GET"
        assert outgoing[0].headers["authorization"] == "Bearer " + TOKEN
        with pytest.raises(LoanHubReadError):
            await adapter.list_customer_loans(
                tenant_id=TENANT, customer_id=OTHER_BORROWER)
        state["active"] = False
        with pytest.raises(LoanHubReadError):
            await adapter.list_customer_loans(
                tenant_id=TENANT, customer_id=BORROWER)
        state["active"] = True
        state["role"] = "superadmin"
        with pytest.raises(LoanHubReadError):
            await adapter.list_customer_loans(
                tenant_id=TENANT, customer_id=BORROWER)
    finally:
        await client.aclose()
    assert len(outgoing) == 1
