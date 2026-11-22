"""Employee directory HTTP boundary: default off, real server-side session, no PII."""
from types import MethodType
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.staff_login_routes import (
    COOKIE, StaffLoginConfig, StagingStaffSessionStore,
)
from backend.app.loanhub_staff_clients import LoanHubStaffClientDirectory
from backend.app.loanhub_staff_verifier import (
    LoanHubStaffVerifier, StaffVerificationUnavailable,
)
from backend.app.staff_authorization import VerifiedStaffIdentity

ORIGIN = "https://batlokoa-staging.example"
LOANHUB = "https://loanhub-staging.example"
COMPANY, BRANCH, DIFFERENT_BRANCH, EMPLOYEE = (uuid4() for _ in range(4))


@pytest.fixture(autouse=True)
def reset_staging_config():
    for name in ("staff_login_config", "staff_client_directory",
                 "staff_client_directory_enabled"):
        if hasattr(app.state, name):
            delattr(app.state, name)
    yield
    for name in ("staff_login_config", "staff_client_directory",
                 "staff_client_directory_enabled"):
        if hasattr(app.state, name):
            delattr(app.state, name)


def enabled(*, identity=None, records=None, upstream_status=200):
    identity = identity or VerifiedStaffIdentity(
        user_id=EMPLOYEE, company_id=COMPANY, role="LOAN_OFFICER",
        active=True, branch_ids=frozenset({BRANCH}),
    )
    verifier = LoanHubStaffVerifier(
        origin=LOANHUB, public_key="test-only",
        batlokoa_company_id=COMPANY,
    )
    verifier.verify = MethodType(lambda self, token: identity, verifier)
    store = StagingStaffSessionStore()
    session_cookie, _ = store.issue("synthetic-only-token", 300)
    config = StaffLoginConfig(ORIGIN, LOANHUB, verifier, store)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(upstream_status, json=records if records is not None else [])

    client = httpx.Client(transport=httpx.MockTransport(respond))
    app.state.staff_login_config = config
    app.state.staff_client_directory = LoanHubStaffClientDirectory(
        origin=LOANHUB, client=client,
    )
    app.state.staff_client_directory_enabled = True
    return TestClient(app, base_url=ORIGIN), session_cookie, calls, client


def test_default_route_stays_off_even_if_browser_claims_staff_headers():
    client = TestClient(app, base_url=ORIGIN)
    response = client.get("/api/v1/staff/clients", headers={
        "Authorization": "Bearer forged",
        "X-Company-ID": str(COMPANY),
        "X-Active-Role": "company_owner",
    })
    assert response.status_code == 503
    assert response.json() == {"code": "STAFF_CLIENT_DIRECTORY_DISABLED"}
    assert response.headers["cache-control"] == "no-store"


def test_directory_requires_cookie_not_browser_bearer_or_claimed_company():
    client, _, calls, upstream = enabled()
    try:
        result = client.get("/api/v1/staff/clients", headers={
            "Authorization": "Bearer forged",
            "X-Company-ID": str(COMPANY),
        })
        assert result.status_code == 401
        assert calls == []
    finally:
        upstream.close()


def test_verified_session_can_read_only_minimal_branch_scoped_fields():
    record = {
        "id": str(uuid4()), "company_id": str(COMPANY),
        "branch_id": str(BRANCH), "full_name": "Synthetic Person",
        "account_reference": "TEST-001", "status": "active",
        "national_id": "SENSITIVE-NOT-FOR-GATEWAY",
        "phone": "SENSITIVE-NOT-FOR-GATEWAY",
    }
    client, cookie, calls, upstream = enabled(records=[record])
    try:
        client.cookies.set(COOKIE, cookie)
        response = client.get("/api/v1/staff/clients?search=Synthetic")
        assert response.status_code == 200
        assert response.json() == {"clients": [{
            "account_id": record["id"],
            "company_id": str(COMPANY),
            "branch_id": str(BRANCH),
            "full_name": "Synthetic Person",
            "account_reference": "TEST-001",
            "status": "active",
        }]}
        assert "SENSITIVE-NOT-FOR-GATEWAY" not in response.text
        assert response.headers["cache-control"] == "no-store"
        assert len(calls) == 1
        assert calls[0].url.params["branch_id"] == str(BRANCH)
        assert calls[0].headers["authorization"] == "Bearer synthetic-only-token"
    finally:
        upstream.close()


def test_cross_branch_and_upstream_scope_mismatch_fail_closed():
    client, cookie, calls, upstream = enabled()
    try:
        client.cookies.set(COOKIE, cookie)
        forbidden = client.get(
            "/api/v1/staff/clients", params={"branch_id": str(DIFFERENT_BRANCH)},
        )
        assert forbidden.status_code == 403
        assert calls == []
    finally:
        upstream.close()

    record = {
        "id": str(uuid4()), "company_id": str(uuid4()),
        "branch_id": str(BRANCH), "full_name": "Other Tenant",
        "account_reference": "UNTRUSTED", "status": "active",
    }
    client, cookie, calls, upstream = enabled(records=[record])
    try:
        client.cookies.set(COOKIE, cookie)
        assert client.get("/api/v1/staff/clients").status_code == 503
        assert len(calls) == 1
    finally:
        upstream.close()


def test_rejected_upstream_request_and_bad_query_never_expose_client_details():
    client, cookie, calls, upstream = enabled(
        records={"detail": "Sensitive upstream response"},
        upstream_status=403,
    )
    try:
        client.cookies.set(COOKIE, cookie)
        response = client.get("/api/v1/staff/clients")
        assert response.status_code == 503
        assert "Sensitive upstream response" not in response.text
        assert client.get("/api/v1/staff/clients?limit=101").status_code == 422
    finally:
        upstream.close()


def test_opt_in_without_trusted_session_configuration_stays_disabled():
    app.state.staff_client_directory_enabled = True
    app.state.staff_client_directory = LoanHubStaffClientDirectory(origin=LOANHUB)
    assert TestClient(app, base_url=ORIGIN).get("/api/v1/staff/clients").status_code == 503


def test_company_owner_can_read_cross_branch_minimal_directory():
    """The signed LoanHub company-owner role may read company-wide results."""
    owner = VerifiedStaffIdentity(
        user_id=EMPLOYEE, company_id=COMPANY, role="COMPANY_OWNER",
        active=True, branch_ids=frozenset(), company_wide_scope=True,
    )
    records = [
        {
            "id": str(uuid4()), "company_id": str(COMPANY),
            "branch_id": str(BRANCH), "full_name": "Synthetic Branch A",
            "account_reference": "TEST-A", "status": "active",
            "national_id": "PRIVATE-NATIONAL-ID-A",
            "phone": "PRIVATE-PHONE-A",
        },
        {
            "id": str(uuid4()), "company_id": str(COMPANY),
            "branch_id": str(DIFFERENT_BRANCH), "full_name": "Synthetic Branch B",
            "account_reference": "TEST-B", "status": "active",
            "national_id": "PRIVATE-NATIONAL-ID-B",
        },
    ]
    client, cookie, calls, upstream = enabled(identity=owner, records=records)
    try:
        client.cookies.set(COOKIE, cookie)
        response = client.get("/api/v1/staff/clients", params={"limit": 30})
        assert response.status_code == 200
        summaries = response.json()["clients"]
        assert len(summaries) == 2
        assert {item["branch_id"] for item in summaries} == {
            str(BRANCH), str(DIFFERENT_BRANCH),
        }
        assert {item["full_name"] for item in summaries} == {
            "Synthetic Branch A", "Synthetic Branch B",
        }
        assert calls[0].headers["X-Company-ID"] == str(COMPANY)
        assert calls[0].headers["X-Active-Role"] == "company_owner"
        assert "branch_id" not in calls[0].url.params
        assert "PRIVATE" not in response.text
        assert all(set(item.keys()) == {
            "account_id", "account_reference", "company_id",
            "branch_id", "full_name", "status",
        } for item in summaries)
    finally:
        upstream.close()


def test_company_owner_cannot_read_records_from_other_companies():
    owner = VerifiedStaffIdentity(
        user_id=EMPLOYEE, company_id=COMPANY, role="COMPANY_OWNER",
        active=True, branch_ids=frozenset(), company_wide_scope=True,
    )
    records = [{
        "id": str(uuid4()), "company_id": str(uuid4()),
        "branch_id": str(BRANCH), "full_name": "Wrong Company",
        "account_reference": "CROSS-TENANT", "status": "active",
    }]
    client, cookie, calls, upstream = enabled(identity=owner, records=records)
    try:
        client.cookies.set(COOKIE, cookie)
        result = client.get("/api/v1/staff/clients")
        assert result.status_code == 503
        assert result.json() == {"code": "CLIENT_DIRECTORY_UNAVAILABLE"}
        assert "Wrong Company" not in result.text
        assert len(calls) == 1
    finally:
        upstream.close()


def test_company_owner_explicit_branch_filter_is_enforced_on_results():
    owner = VerifiedStaffIdentity(
        user_id=EMPLOYEE, company_id=COMPANY, role="COMPANY_OWNER",
        active=True, branch_ids=frozenset(), company_wide_scope=True,
    )
    records = [{
        "id": str(uuid4()), "company_id": str(COMPANY),
        "branch_id": str(DIFFERENT_BRANCH), "full_name": "Wrong Branch",
        "account_reference": "WRONG-BRANCH", "status": "active",
    }]
    client, cookie, calls, upstream = enabled(identity=owner, records=records)
    try:
        client.cookies.set(COOKIE, cookie)
        result = client.get("/api/v1/staff/clients", params={"branch_id": str(BRANCH)})
        assert result.status_code == 503
        assert result.json() == {"code": "CLIENT_DIRECTORY_UNAVAILABLE"}
        assert calls[0].url.params["branch_id"] == str(BRANCH)
    finally:
        upstream.close()
