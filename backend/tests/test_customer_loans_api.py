from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from backend.app.contracts import LoanSummary, Money
from backend.app.customer_loans_api import ReadRouteConfig
from backend.app.identity import CustomerContext
from backend.app.loan_reads import LoanReadService
from backend.app.loanhub_adapter import LoanHubReadError
from backend.app.main import app

ISSUER = "https://auth.test.example"
AUDIENCE = "batlokoa-gateway"
COMPANY = "d921126e-e1a7-482e-ad1b-6e99b1682e19"
BORROWER = "cb6700f8-1808-46ca-bfc2-f030ad0e2d7c"
PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class Directory:
    def __init__(self, mapping):
        self.mapping = mapping

    async def lookup(self, *, issuer, subject):
        return self.mapping


class Adapter:
    def __init__(self, records=None, fail=False):
        self.records = records if records is not None else []
        self.fail = fail
        self.calls = []

    async def list_customer_loans(self, *, tenant_id, customer_id):
        self.calls.append((tenant_id, customer_id))
        if self.fail:
            raise LoanHubReadError("Upstream error")
        return self.records


@pytest.fixture(autouse=True)
def no_leaked_auth_configuration():
    if hasattr(app.state, "loan_read_config"):
        del app.state.loan_read_config
    yield
    if hasattr(app.state, "loan_read_config"):
        del app.state.loan_read_config


def token(*, key=PRIVATE, subject="subject-1", audience=AUDIENCE, expiry=None):
    now = datetime.now(timezone.utc)
    return jwt.encode({
        "iss": ISSUER, "aud": audience, "sub": subject, "iat": now,
        "exp": expiry or (now + timedelta(minutes=2)),
    }, key, algorithm="RS256")


def configure(*, mapping=None, records=None, fail=False):
    if mapping is None:
        mapping = CustomerContext(
            tenant_id=COMPANY, customer_id=BORROWER,
            auth_subject="subject-1",
        )
    adapter = Adapter(records=records, fail=fail)
    app.state.loan_read_config = ReadRouteConfig(
        issuer=ISSUER, audience=AUDIENCE, public_key=PRIVATE.public_key(),
        service=LoanReadService(tenant_id=COMPANY,
                                directory=Directory(mapping), adapter=adapter),
    )
    return adapter


def get_loans(bearer):
    return TestClient(app).get("/api/v1/me/loans", headers={"Authorization": f"Bearer {bearer}"})


def test_disabled_even_with_valid_bearer():
    response = get_loans(token())
    assert response.status_code == 503
    assert response.json()["code"] == "INTEGRATION_DISABLED"
    assert response.headers["cache-control"] == "no-store"


def test_valid_customer_only_sees_server_mapped_loans():
    row = LoanSummary(
        loan_id="42", status="active",
        outstanding=Money(currency="LSL", minor_units=580005),
    )
    adapter = configure(records=[row])
    response = get_loans(token())
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["loans"][0]["outstanding"]["minor_units"] == 580005
    assert adapter.calls == [(COMPANY, BORROWER)]


@pytest.mark.parametrize("bad", [
    lambda: token(key=OTHER),
    lambda: token(audience="some-other-app"),
    lambda: token(expiry=datetime.now(timezone.utc)-timedelta(minutes=1)),
])
def test_bad_signature_audience_or_expiry_fails_before_loan_adapter(bad):
    adapter = configure()
    response = get_loans(bad())
    assert response.status_code == 401
    assert adapter.calls == []


def test_no_authorization_header_rejected():
    adapter = configure()
    response = TestClient(app).get("/api/v1/me/loans")
    assert response.status_code == 401
    assert adapter.calls == []


def test_cross_tenant_mapping_rejected_without_upstream_call():
    adapter = configure(mapping=CustomerContext(
        tenant_id="other-company", customer_id=BORROWER, auth_subject="subject-1"))
    response = get_loans(token())
    assert response.status_code == 403
    assert adapter.calls == []


def test_upstream_failure_returns_503_not_demo_balance():
    adapter = configure(fail=True)
    response = get_loans(token())
    assert response.status_code == 503
    assert response.json()["code"] == "LOAN_SERVICE_UNAVAILABLE"
    assert "5800" not in response.text
    assert adapter.calls == [(COMPANY, BORROWER)]


def test_payment_routes_remain_disabled_when_loan_read_config_exists():
    configure()
    response = TestClient(app).post("/api/v1/payments/intents", json={})
    assert response.status_code == 503
    assert response.json()["code"] == "INTEGRATION_DISABLED"
