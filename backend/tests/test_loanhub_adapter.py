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
