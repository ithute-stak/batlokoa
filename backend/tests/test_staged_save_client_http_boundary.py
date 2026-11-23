"""Isolated HTTP certification of the disabled Batlokoa Save Client route.

Build a temporary FastAPI app containing the draft router for this test ONLY.
The deployed main application never mounts it. Synthetic staff and client
identifiers, never actual LoanHub credentials or customer data.
"""
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app import staff_client_creation_routes as routes
from backend.app.staff_authorization import VerifiedStaffIdentity
from backend.app.staff_login_routes import COOKIE, CSRF_COOKIE

PATH = "/api/v1/staff/clients/register"
COMPANY, ACTOR, BRANCH, ACCOUNT = (uuid4() for _ in range(4))
CSRF = "synthetic-csrf-token-for-isolated-tests"
SESSION = "synthetic-session-token-for-isolated-tests"


def isolated_client(monkeypatch, *, released):
    app = FastAPI()
    app.include_router(routes.router)
    staff = VerifiedStaffIdentity(
        user_id=ACTOR, company_id=COMPANY, role="LOAN_OFFICER",
        active=True, branch_ids=frozenset({BRANCH}),
    )
    record = SimpleNamespace(
        csrf_token=CSRF, access_token="synthetic-never-real-jwt",
    )
    store = SimpleNamespace(resolve=lambda session: (
        record if session == SESSION else None))
    cfg = SimpleNamespace(
        public_origin="https://batlokoa.test",
        loanhub_origin="https://loanhub.test",
        store=store,
        verifier=SimpleNamespace(verify=lambda token: staff),
    )
    monkeypatch.setattr(routes, "_config", lambda request: cfg)
    # True is a test-only override in an isolated in-memory FastAPI object.
    # This override is NEVER added to production app configuration or source.
    monkeypatch.setattr(routes, "_release_approved", lambda: released)
    client = TestClient(app, base_url="https://batlokoa.test")
    client.cookies.set(COOKIE, SESSION)
    client.cookies.set(CSRF_COOKIE, CSRF)
    return client


def headers(*, csrf=CSRF):
    return {
        "origin": "https://batlokoa.test",
        "x-csrf-token": csrf,
        "idempotency-key": "synthetic-save-request-00001",
    }


def body():
    return {
        "branch_id": str(BRANCH),
        "first_name": "Synthetic",
        "last_name": "Applicant",
        "national_id": "SYNTHETIC-NOT-A-REAL-NATIONAL-ID",
    }


def test_live_default_gate_never_invokes_creation_transport(monkeypatch):
    client = isolated_client(monkeypatch, released=False)
    def forbidden(**kwargs):
        raise AssertionError("Save transport called despite deny gate")
    monkeypatch.setattr(routes, "post_new_only_client", forbidden)
    response = client.post(PATH, headers=headers(), json=body())
    assert response.status_code == 503
    assert response.json()["code"] == "NEW_ONLY_REGISTRATION_NOT_RELEASED"


def test_staging_http_save_preserves_staff_auth_and_request_scope(monkeypatch):
    client = isolated_client(monkeypatch, released=True)
    calls = []
    def synthetic_transport(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(account_id=ACCOUNT, replayed=False)
    monkeypatch.setattr(routes, "post_new_only_client", synthetic_transport)
    response = client.post(PATH, headers=headers(), json=body())
    assert response.status_code == 201
    assert response.json() == {
        "registered": True, "client_account_id": str(ACCOUNT),
        "replayed": False,
    }
    assert len(calls) == 1
    assert calls[0]["branch_id"] == BRANCH
    assert calls[0]["complete_payload"] == body()
    assert calls[0]["idempotency_key"] == "synthetic-save-request-00001"
    assert calls[0]["loanhub_access_token"] == "synthetic-never-real-jwt"
    assert calls[0]["independently_approved_release"] is True


def test_staging_http_save_blocks_missing_csrf_before_any_upstream_write(
    monkeypatch,
):
    client = isolated_client(monkeypatch, released=True)
    def forbidden(**kwargs):
        raise AssertionError("CSRF rejection must happen before transport")
    monkeypatch.setattr(routes, "post_new_only_client", forbidden)
    response = client.post(PATH, headers=headers(csrf="wrong-token"),
                           json=body())
    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_REJECTED"


def test_staging_http_save_blocks_foreign_origin_before_any_upstream_write(
    monkeypatch,
):
    client = isolated_client(monkeypatch, released=True)
    def forbidden(**kwargs):
        raise AssertionError("Cross-site rejection must precede transport")
    monkeypatch.setattr(routes, "post_new_only_client", forbidden)
    bad = {**headers(), "origin": "https://foreign.example"}
    response = client.post(PATH, headers=bad, json=body())
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN_ORIGIN"
