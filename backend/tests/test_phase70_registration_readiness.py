"""Registration release visibility is informational, scoped and read-only."""
from types import MethodType
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app import staff_registration_readiness_routes as routes
from backend.app.loanhub_staff_verifier import LoanHubStaffVerifier
from backend.app.staff_authorization import VerifiedStaffIdentity
from backend.app.staff_login_routes import (
    COOKIE, StaffLoginConfig, StagingStaffSessionStore,
)

COMPANY, USER, BRANCH = (uuid4() for _ in range(3))
ORIGIN = "https://batlokoa-readiness.example"
UPSTREAM = "https://loanhub-readiness.example"
PATH = "/api/v1/staff/clients/registration-readiness"


@pytest.fixture(autouse=True)
def clean():
    if hasattr(app.state, "staff_login_config"):
        del app.state.staff_login_config
    yield
    if hasattr(app.state, "staff_login_config"):
        del app.state.staff_login_config


def setup(monkeypatch, *, upstream_status=200, body=None):
    calls = []
    data = {
        "new_only_registration_available": False,
        "can_submit_new_only_registration": False,
        "requires_identity_migration_approval": True,
        "requires_independent_release_approval": True,
        "reason_code": "NEW_ONLY_REGISTRATION_NOT_RELEASED",
    } if body is None else body

    class UpstreamClient:
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False
            assert kwargs["follow_redirects"] is False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url, headers):
            calls.append((url, headers))
            return httpx.Response(upstream_status, json=data)

    verifier = LoanHubStaffVerifier(
        origin=UPSTREAM, public_key="synthetic-test-key",
        batlokoa_company_id=COMPANY,
    )

    def verify(self, token):
        return VerifiedStaffIdentity(
            user_id=USER, company_id=COMPANY, role="LOAN_OFFICER",
            active=True, branch_ids=frozenset({BRANCH}),
        )

    verifier.verify = MethodType(verify, verifier)
    store = StagingStaffSessionStore()
    cookie, csrf = store.issue("synthetic-access", 300)
    app.state.staff_login_config = StaffLoginConfig(ORIGIN, UPSTREAM, verifier, store)
    client = TestClient(app, base_url=ORIGIN)
    client.cookies.set(COOKIE, cookie)
    # Route is GET-only. No PII or body sent to upstream.
    monkeypatch.setattr(routes.httpx, "Client", UpstreamClient)
    return client, calls


def test_readiness_is_protected_informational_and_no_pii(monkeypatch):
    client, calls = setup(monkeypatch)
    result = client.get(PATH, headers={"Origin": ORIGIN})
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    assert result.json() == {
        "registration_available": False,
        "can_create_client": False,
        "reason_code": "NEW_ONLY_REGISTRATION_NOT_RELEASED",
        "requires_identity_migration_approval": True,
        "requires_independent_release_approval": True,
    }
    assert len(calls) == 1
    url, headers = calls[0]
    assert url == UPSTREAM + "/api/v1/batlokoa/registration/availability"
    assert headers["X-Company-ID"] == str(COMPANY)
    assert headers["Authorization"] == "Bearer synthetic-access"
    assert "national_id" not in str(calls)


def test_expired_session_and_foreign_origin_cannot_call_upstream(monkeypatch):
    client, calls = setup(monkeypatch)
    result = client.get(PATH, headers={"Origin": "https://attacker.example"})
    assert result.status_code == 403
    assert calls == []
    client.cookies.delete(COOKIE)
    assert client.get(PATH, headers={"Origin": ORIGIN}).status_code == 401
    assert calls == []


@pytest.mark.parametrize("upstream_status,body", [
    (403, {}),
    (200, {
        "new_only_registration_available": True,
        "can_submit_new_only_registration": True,
        "requires_identity_migration_approval": False,
        "requires_independent_release_approval": False,
        "reason_code": "NEW_ONLY_REGISTRATION_NOT_RELEASED",
    }),
    (200, {"reason_code": "RELEASED"}),
    (200, {
        "new_only_registration_available": "false",
        "can_submit_new_only_registration": False,
        "requires_identity_migration_approval": True,
        "requires_independent_release_approval": True,
        "reason_code": "NEW_ONLY_REGISTRATION_NOT_RELEASED",
    }),
])
def test_untrusted_upstream_fails_closed(monkeypatch, upstream_status, body):
    client, calls = setup(monkeypatch, upstream_status=upstream_status, body=body)
    response = client.get(PATH, headers={"Origin": ORIGIN})
    assert response.status_code == 503
    assert response.json() == {"code": "REGISTRATION_READINESS_UNAVAILABLE"}
    assert len(calls) == 1
