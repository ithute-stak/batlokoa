import pytest

from backend.app.contracts import LoanSummary, Money
from backend.app.identity import CustomerContext, VerifiedClaims
from backend.app.loan_reads import (
    LoanReadForbidden,
    LoanReadService,
    LoanReadUnavailable,
)


def claims(subject="customer-one"):
    # Identity primitive unit tests verify signature separately. These claims
    # represent data that has already passed the signed-token verifier.
    return VerifiedClaims(sub=subject, iss="https://auth.example.test",
                          aud="batlokoa-gateway", iat=1900000000, exp=1900000900)


class Directory:
    def __init__(self, context):
        self.context = context
        self.calls = []

    async def lookup(self, *, issuer, subject):
        self.calls.append((issuer, subject))
        return self.context


class LoanHubStub:
    def __init__(self, records):
        self.records = records
        self.calls = []

    async def list_customer_loans(self, *, tenant_id, customer_id):
        self.calls.append((tenant_id, customer_id))
        return self.records


def loan(id="loan-001"):
    return LoanSummary(loan_id=id, status="active",
                       outstanding=Money(currency="LSL", minor_units=580000))


@pytest.mark.asyncio
async def test_authorized_read_binds_to_server_mapping_only():
    directory = Directory(CustomerContext(tenant_id="batlokoa", customer_id="internal-42",
                                          auth_subject="customer-one"))
    upstream = LoanHubStub([loan()])
    service = LoanReadService(tenant_id="batlokoa", directory=directory, adapter=upstream)
    result = await service.list_my_loans(claims=claims())
    assert result[0].outstanding.minor_units == 580000
    assert upstream.calls == [("batlokoa", "internal-42")]
    assert directory.calls == [("https://auth.example.test", "customer-one")]


@pytest.mark.asyncio
@pytest.mark.parametrize("mapping", [
    None,
    CustomerContext("different-tenant", "internal-42", "customer-one"),
    CustomerContext("batlokoa", "internal-42", "someone-else"),
    CustomerContext("batlokoa", "", "customer-one"),
])
async def test_missing_wrong_tenant_or_wrong_subject_never_calls_upstream(mapping):
    upstream = LoanHubStub([loan()])
    service = LoanReadService(tenant_id="batlokoa", directory=Directory(mapping),
                              adapter=upstream)
    with pytest.raises(LoanReadForbidden):
        await service.list_my_loans(claims=claims())
    assert upstream.calls == []


@pytest.mark.asyncio
async def test_upstream_untrusted_records_are_strictly_validated():
    directory = Directory(CustomerContext("batlokoa", "internal-42", "customer-one"))
    for records in (
        [{"loan_id": "x", "status": "active", "outstanding":
          {"currency": "USD", "minor_units": 100}}],
        [{"loan_id": "x", "status": "active", "outstanding":
          {"currency": "LSL", "minor_units": -1}}],
        [loan("same"), loan("same")],
        [loan(), loan("second")],
        {"loans": [loan()]},
    ):
        service = LoanReadService(tenant_id="batlokoa", directory=directory,
                                  adapter=LoanHubStub(records), max_loans=1)
        with pytest.raises(LoanReadUnavailable):
            await service.list_my_loans(claims=claims())


@pytest.mark.asyncio
async def test_configuration_defaults_are_fail_closed():
    directory = Directory(CustomerContext("batlokoa", "internal-42", "customer-one"))
    upstream = LoanHubStub([loan()])
    service = LoanReadService(tenant_id="", directory=directory, adapter=upstream)
    with pytest.raises(LoanReadUnavailable):
        await service.list_my_loans(claims=claims())
    assert upstream.calls == []


@pytest.mark.asyncio
async def test_empty_authorized_loan_list_is_valid_not_demo_data():
    directory = Directory(CustomerContext("batlokoa", "internal-42", "customer-one"))
    service = LoanReadService(tenant_id="batlokoa", directory=directory,
                              adapter=LoanHubStub([]))
    assert await service.list_my_loans(claims=claims()) == []
