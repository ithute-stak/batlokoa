import json
from uuid import UUID

import httpx
import pytest

from backend.app.loanhub_adapter import LoanHubBorrowerReadAdapter, LoanHubReadError

COMPANY = "d921126e-e1a7-482e-ad1b-6e99b1682e19"
BORROWER = "cb6700f8-1808-46ca-bfc2-f030ad0e2d7c"
LOAN = "72de5a5b-ad44-4eea-b871-81479fe7b045"


def record(**overrides):
    payload = {
        "id": LOAN, "company_id": COMPANY, "borrower_id": BORROWER,
        "status": "active", "balance": "5800.05",
    }
    payload.update(overrides)
    return payload


def adapter(handler, *, token="borrower-scoped-token"):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = LoanHubBorrowerReadAdapter(
        base_url="https://loanhub.example.test",
        borrower_token_for=lambda tenant, borrower: token,
        client=client,
    )
    return service, client


@pytest.mark.asyncio
async def test_real_loanhub_contract_reads_borrower_scoped_list_only():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=[record()])

    service, client = adapter(handler)
    try:
        result = await service.list_customer_loans(tenant_id=COMPANY, customer_id=BORROWER)
    finally:
        await client.aclose()
    assert len(result) == 1
    assert result[0].outstanding.currency == "LSL"
    assert result[0].outstanding.minor_units == 580005
    assert result[0].loan_id == LOAN
    assert len(calls) == 1
    assert calls[0].method == "GET"
    assert calls[0].url.path == "/api/v1/loans/"
    assert calls[0].url.params["skip"] == "0"
    assert calls[0].url.params["limit"] == "100"
    assert calls[0].headers["authorization"] == "Bearer borrower-scoped-token"
    assert "X-Company-ID" not in calls[0].headers


@pytest.mark.asyncio
async def test_empty_borrower_loans_are_valid():
    service, client = adapter(lambda req: httpx.Response(200, json=[]))
    try:
        assert await service.list_customer_loans(tenant_id=COMPANY, customer_id=BORROWER) == []
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("records", [
    [record(company_id="9ff995dc-ad87-4a91-8a8f-18ddfc85d991")],
    [record(borrower_id="9ff995dc-ad87-4a91-8a8f-18ddfc85d991")],
    [record(balance="-0.01")],
    [record(balance="1.001")],
    [record(balance="NaN")],
    [record(balance=None)],
    [record(id="not-a-uuid")],
    [record(), record()],
    [record(status="")],
    {"loans": [record()]},
    [record()] * 100,
])
async def test_unsafe_upstream_data_is_rejected(records):
    service, client = adapter(lambda req: httpx.Response(200, json=records))
    try:
        with pytest.raises(LoanHubReadError):
            await service.list_customer_loans(tenant_id=COMPANY, customer_id=BORROWER)
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [301, 401, 403, 404, 429, 500])
async def test_unsuccessful_http_response_rejected(status):
    service, client = adapter(lambda req: httpx.Response(status, headers={"Location": "https://elsewhere.test"}))
    try:
        with pytest.raises(LoanHubReadError):
            await service.list_customer_loans(tenant_id=COMPANY, customer_id=BORROWER)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_missing_approved_borrower_token_never_calls_upstream():
    called = []
    service, client = adapter(lambda req: called.append(req) or httpx.Response(200, json=[]), token=None)
    try:
        with pytest.raises(LoanHubReadError):
            await service.list_customer_loans(tenant_id=COMPANY, customer_id=BORROWER)
    finally:
        await client.aclose()
    assert called == []


@pytest.mark.asyncio
async def test_invalid_mapped_uuid_never_calls_upstream():
    called = []
    service, client = adapter(lambda req: called.append(req) or httpx.Response(200, json=[]))
    try:
        with pytest.raises(LoanHubReadError):
            await service.list_customer_loans(tenant_id="batlokoa", customer_id=BORROWER)
    finally:
        await client.aclose()
    assert called == []


@pytest.mark.parametrize("origin", [
    "http://loanhub.example.test", "https://loanhub.example.test/path",
    "https://user:pass@loanhub.example.test", "https://loanhub.example.test?q=x",
])
def test_invalid_upstream_origin_rejected(origin):
    with pytest.raises(ValueError):
        LoanHubBorrowerReadAdapter(base_url=origin, borrower_token_for=lambda a, b: "token")


@pytest.mark.asyncio
async def test_json_float_precision_kept_without_binary_rounding():
    def handler(request):
        return httpx.Response(200, content=(
            '[{"id":"' + LOAN + '","company_id":"' + COMPANY
            + '","borrower_id":"' + BORROWER
            + '","status":"active","balance":0.29}]'
        ).encode(), headers={"content-type": "application/json"})
    service, client = adapter(handler)
    try:
        rows = await service.list_customer_loans(tenant_id=COMPANY, customer_id=BORROWER)
    finally:
        await client.aclose()
    assert rows[0].outstanding.minor_units == 29


@pytest.mark.asyncio
async def test_borrower_credential_broker_is_called_with_exact_verified_mapping():
    second_borrower = "9ff995dc-ad87-4a91-8a8f-18ddfc85d991"
    issued = {
        (COMPANY, BORROWER): "token-for-first-borrower",
        (COMPANY, second_borrower): "token-for-second-borrower",
    }
    calls, requests = [], []

    def grant(tenant, borrower):
        calls.append((tenant, borrower))
        return issued.get((tenant, borrower))

    def handler(request):
        requests.append(request)
        if request.headers["authorization"] == "Bearer token-for-first-borrower":
            return httpx.Response(200, json=[record()])
        return httpx.Response(200, json=[record(
            borrower_id=second_borrower,
            id="9ff995dc-ad87-4a91-8a8f-18ddfc85d992",
        )])

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = LoanHubBorrowerReadAdapter(
        base_url="https://loanhub.example.test",
        borrower_token_for=grant,
        client=client,
    )
    try:
        first = await service.list_customer_loans(
            tenant_id=COMPANY, customer_id=BORROWER)
        second = await service.list_customer_loans(
            tenant_id=COMPANY, customer_id=second_borrower)
    finally:
        await client.aclose()
    assert len(first) == len(second) == 1
    assert calls == [(COMPANY, BORROWER), (COMPANY, second_borrower)]
    assert [r.headers["authorization"] for r in requests] == [
        "Bearer token-for-first-borrower",
        "Bearer token-for-second-borrower",
    ]


@pytest.mark.asyncio
async def test_revoked_borrower_credential_never_calls_loanhub():
    outgoing = []
    grants = {(COMPANY, BORROWER): "active-borrower-token"}
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: outgoing.append(request) or httpx.Response(200, json=[])))
    service = LoanHubBorrowerReadAdapter(
        base_url="https://loanhub.example.test",
        borrower_token_for=lambda tenant, borrower: grants.get((tenant, borrower)),
        client=client,
    )
    try:
        assert await service.list_customer_loans(
            tenant_id=COMPANY, customer_id=BORROWER) == []
        del grants[(COMPANY, BORROWER)]
        with pytest.raises(LoanHubReadError):
            await service.list_customer_loans(
                tenant_id=COMPANY, customer_id=BORROWER)
    finally:
        await client.aclose()
    assert len(outgoing) == 1


@pytest.mark.asyncio
async def test_credential_broker_failure_is_sanitized_and_never_calls_upstream():
    outgoing = []
    def broken_broker(_tenant, _borrower):
        raise RuntimeError("internal-credential-store-secret")

    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda req: outgoing.append(req) or httpx.Response(200, json=[])))
    service = LoanHubBorrowerReadAdapter(
        base_url="https://loanhub.example.test",
        borrower_token_for=broken_broker, client=client)
    try:
        with pytest.raises(LoanHubReadError) as exc:
            await service.list_customer_loans(
                tenant_id=COMPANY, customer_id=BORROWER)
        assert "internal-credential-store-secret" not in str(exc.value)
    finally:
        await client.aclose()
    assert outgoing == []
