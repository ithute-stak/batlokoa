"""Contract tests use isolated fake sessions, not real credentials or LoanHub."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.auth_routes import SESSION_COOKIE
from backend.app.contracts import LoanSummary, Money
from backend.app.identity import CustomerContext, NoCustomersDirectory
from backend.app.loan_reads import LoanReadService
from backend.app.main import app
from backend.app.session_loan_reads import SessionLoanReadConfig

TENANT = "d921126e-e1a7-482e-ad1b-6e99b1682e19"
BORROWER = "cb6700f8-1808-46ca-bfc2-f030ad0e2d7c"
ORIGIN = "https://testserver"
COOKIE = "opaque-test-session-token-of-sufficient-length"


class Sessions:
    def __init__(self, context=None, *, fail=False):
        self.context = context
        self.fail = fail
        self.calls = []

    async def resolve(self, token, **kwargs):
        self.calls.append(token)
        if self.fail:
            raise RuntimeError("Database unavailable")
        if token != COOKIE or self.context is None:
            return None
        from backend.app.sessions import ActiveSession
        return ActiveSession(context=self.context, central_sid=uuid4())


class Adapter:
    def __init__(self, records=None):
        self.records = [] if records is None else records
        self.calls = []

    async def list_customer_loans(self, *, tenant_id, customer_id):
        self.calls.append((tenant_id, customer_id))
        return self.records


@pytest.fixture(autouse=True)
def clean_config():
    if hasattr(app.state, "session_loan_read_config"):
        del app.state.session_loan_read_config
    yield
    if hasattr(app.state, "session_loan_read_config"):
        del app.state.session_loan_read_config


def configure(context=None, records=None, *, fail=False):
    if context is None:
        context = CustomerContext(TENANT, BORROWER, "verified-subject")
    sessions = Sessions(context, fail=fail)
    adapter = Adapter(records)
    service = LoanReadService(
        tenant_id=TENANT, directory=NoCustomersDirectory(), adapter=adapter)
    app.state.session_loan_read_config = SessionLoanReadConfig(
        sessions=sessions, service=service, public_origin=ORIGIN)
    return sessions, adapter


def request(*, cookie=True, headers=None, params=None):
    default = {"Sec-Fetch-Site": "same-origin"}
    default.update(headers or {})
    return TestClient(app, base_url=ORIGIN).get(
        "/api/v1/me/loans/session", headers=default,
        cookies={SESSION_COOKIE: COOKIE} if cookie else None,
        params=params)


def test_default_unconfigured_route_is_disabled():
    response = request()
    assert response.status_code == 503
    assert response.json() == {"code": "INTEGRATION_DISABLED"}
    assert response.headers["cache-control"] == "no-store"


def test_cookie_session_reads_only_server_resolved_borrower():
    row = LoanSummary(
        loan_id="test-loan", status="active",
        outstanding=Money(currency="LSL", minor_units=2599))
    sessions, adapter = configure(records=[row])
    response = request(
        headers={"Origin": ORIGIN, "X-Tenant-Id": "another-tenant",
                 "X-Customer-Id": "another-borrower"},
        params={"tenant_id": "another-tenant", "customer_id": "another-borrower"})
    assert response.status_code == 200
    assert response.json()["loans"][0]["outstanding"]["minor_units"] == 2599
    assert adapter.calls == [(TENANT, BORROWER)]
    assert sessions.calls == [COOKIE]
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("headers", [
    {"Sec-Fetch-Site": "cross-site"},
    {"Sec-Fetch-Site": "none"},
    {"Sec-Fetch-Site": ""},
    {"Origin": "https://attacker.example"},
    {"Authorization": "Bearer attacker-controlled"},
])
def test_cross_origin_and_bearer_injection_blocked_before_session_lookup(headers):
    sessions, adapter = configure()
    response = request(headers=headers)
    assert response.status_code == 403
    assert sessions.calls == []
    assert adapter.calls == []


def test_no_cookie_and_revoked_session_never_query_loanhub():
    sessions, adapter = configure()
    assert request(cookie=False).status_code == 401
    assert adapter.calls == []
    sessions.context = None
    assert request().status_code == 401
    assert adapter.calls == []


@pytest.mark.parametrize("context", [
    CustomerContext("another-tenant", BORROWER, "verified-subject"),
    CustomerContext(TENANT, "", "verified-subject"),
    CustomerContext(TENANT, BORROWER, ""),
])
def test_cross_tenant_or_incomplete_session_mapping_never_calls_upstream(context):
    sessions, adapter = configure(context=context)
    response = request()
    assert response.status_code == 403
    assert adapter.calls == []


def test_database_failure_and_invalid_upstream_data_do_not_return_demo_loans():
    sessions, adapter = configure(fail=True)
    response = request()
    assert response.status_code == 503
    assert response.json()["code"] == "SESSION_UNAVAILABLE"
    assert adapter.calls == []
    sessions.fail = False
    adapter.records = [{"loan_id": "x", "status": "active",
                        "outstanding": {"currency": "USD", "minor_units": 1}}]
    response = request()
    assert response.status_code == 503
    assert response.json()["code"] == "LOAN_SERVICE_UNAVAILABLE"
    assert "outstanding" not in response.text


def test_read_only_session_configuration_never_enables_writes():
    configure()
    client = TestClient(app, base_url=ORIGIN)
    for route in ("/api/v1/payments/intents", "/api/v1/loans/applications"):
        response = client.post(route, json={})
        assert response.status_code == 503
        assert response.json()["code"] == "INTEGRATION_DISABLED"


def test_session_boundary_rejects_untrusted_http_origin():
    with pytest.raises(ValueError):
        SessionLoanReadConfig(
            sessions=Sessions(), service=LoanReadService(
                tenant_id=TENANT, directory=NoCustomersDirectory(),
                adapter=Adapter()), public_origin="http://testserver")
