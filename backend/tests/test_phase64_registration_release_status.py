"""No-write release status checks reject forged flags and browser identity."""
from types import MethodType
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.loanhub_registration_release_status import (
    LoanHubRegistrationReleaseStatus,
    RegistrationReleaseStatusUnavailable,
)
from backend.app.loanhub_staff_verifier import LoanHubStaffVerifier
from backend.app.staff_login_routes import (
    COOKIE, StaffLoginConfig, StagingStaffSessionStore,
)
from backend.app.staff_authorization import VerifiedStaffIdentity

COMPANY, USER, BRANCH = (uuid4() for _ in range(3))
ORIGIN = "https://batlokoa-release.test"
LOANHUB = "https://loanhub-release.test"


def staff():
    return VerifiedStaffIdentity(
        user_id=USER, company_id=COMPANY, role="LOAN_OFFICER",
        active=True, branch_ids=frozenset({BRANCH}),
    )


def response(*, enabled=False):
    return {
        "new_only_registration_available": enabled,
        "can_submit_new_only_registration": enabled,
        "requires_identity_migration_approval": not enabled,
        "requires_independent_release_approval": not enabled,
        "reason_code": "NEW_ONLY_REGISTRATION_NOT_RELEASED",
    }


def adapter(payload=None, status=200):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json=response() if payload is None else payload)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return LoanHubRegistrationReleaseStatus(origin=LOANHUB, client=client), client, calls


@pytest.fixture(autouse=True)
def clean():
    keys = ("staff_login_config", "staff_registration_release_adapter",
            "staff_registration_release_status_enabled")
    for key in keys:
        if hasattr(app.state, key):
            delattr(app.state, key)
    yield
    for key in keys:
        if hasattr(app.state, key):
            delattr(app.state, key)


def test_disabled_by_default_even_for_browser_supplied_role():
    result = TestClient(app, base_url=ORIGIN).get(
        "/api/v1/staff/clients/registration-release-status",
        headers={"Authorization": "Bearer forged",
                 "X-Company-ID": str(COMPANY),
                 "X-Active-Role": "company_owner"},
    )
    assert result.status_code == 503
    assert result.json()["code"] == "REGISTRATION_RELEASE_STATUS_DISABLED"


def test_real_loan_hub_false_status_keeps_client_creation_disabled():
    review, client, calls = adapter()
    try:
        status = review.inspect(staff=staff(), access_token="verified-token")
        assert status.can_submit is False
        assert status.requires_identity_migration_approval
        assert status.requires_independent_release_approval
        assert calls[0].method == "GET"
        assert calls[0].url.path == "/api/v1/batlokoa/registration/availability"
        assert calls[0].headers["authorization"] == "Bearer verified-token"
    finally:
        client.close()


def test_hypothetical_future_true_status_never_enables_this_gateway():
    review, client, _ = adapter(response(enabled=True))
    try:
        status = review.inspect(staff=staff(), access_token="verified-token")
        assert status.can_submit is False
        assert status.state == "not_released"
    finally:
        client.close()


@pytest.mark.parametrize("payload,code", [
    ({"can_submit_new_only_registration": True}, 200),
    (response() | {"can_submit_new_only_registration": "false"}, 200),
    (response(), 403),
])
def test_bad_or_denied_upstream_status_fails_closed(payload, code):
    review, client, _ = adapter(payload, code)
    try:
        with pytest.raises(RegistrationReleaseStatusUnavailable):
            review.inspect(staff=staff(), access_token="verified-token")
    finally:
        client.close()


def setup_enabled_route():
    verifier = LoanHubStaffVerifier(
        origin=LOANHUB, public_key="test-only",
        batlokoa_company_id=COMPANY,
    )
    verifier.verify = MethodType(lambda self, token: staff(), verifier)
    store = StagingStaffSessionStore()
    session, _csrf = store.issue("synthetic-token", 300)
    app.state.staff_login_config = StaffLoginConfig(
        ORIGIN, LOANHUB, verifier, store,
    )
    review, upstream, calls = adapter()
    app.state.staff_registration_release_adapter = review
    app.state.staff_registration_release_status_enabled = True
    client = TestClient(app, base_url=ORIGIN)
    return client, session, upstream, calls


def test_opt_in_route_requires_cookie_and_never_grants_registration():
    client, cookie, upstream, calls = setup_enabled_route()
    try:
        no_session = client.get(
            "/api/v1/staff/clients/registration-release-status",
            headers={"Authorization": "Bearer forged"},
        )
        assert no_session.status_code == 401
        assert calls == []
        client.cookies.set(COOKIE, cookie)
        result = client.get("/api/v1/staff/clients/registration-release-status")
        assert result.status_code == 200
        assert result.json()["can_submit"] is False
        assert result.json()["client_creation_enabled"] is False
        assert result.headers["cache-control"] == "no-store"
        assert len(calls) == 1
    finally:
        upstream.close()


def test_adapter_origin_mismatch_denies_before_outbound_request():
    client, cookie, upstream, calls = setup_enabled_route()
    try:
        client.cookies.set(COOKIE, cookie)
        other, other_upstream, _ = adapter()
        other._origin = "https://different-loanhub.example"
        try:
            app.state.staff_registration_release_adapter = other
            result = client.get(
                "/api/v1/staff/clients/registration-release-status"
            )
            assert result.status_code == 503
            assert calls == []
        finally:
            other_upstream.close()
    finally:
        upstream.close()
