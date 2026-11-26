from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app import staff_attendance_routes as routes
from backend.app.staff_attendance import AttendanceRejected
from backend.app.staff_attendance_store import AttendanceStore
from backend.app.staff_authorization import VerifiedStaffIdentity
from backend.app.staff_login_routes import COOKIE, CSRF_COOKIE

ORIGIN = "https://batlokoa.example.test"
COMPANY, BRANCH = uuid4(), uuid4()
STAFF = VerifiedStaffIdentity(uuid4(), COMPANY, "LOAN_OFFICER", True,
                              frozenset({BRANCH}))
PATH = "/api/v1/staff/attendance/"


def payload(**changes):
    return dict(branch_id=str(BRANCH), latitude=-29.31, longitude=27.48,
                accuracy_m=2.0, captured_at=datetime.now(timezone.utc).isoformat()) | changes


@pytest.fixture
def configured(monkeypatch):
    app = FastAPI()
    app.include_router(routes.router)
    calls, upstream = [], []
    store = AttendanceStore(lambda: pytest.fail("Unexpected database access"))
    app.state.staff_attendance_enabled = True
    app.state.staff_attendance_store = store
    record = SimpleNamespace(access_token="test-token", csrf_token="test-csrf")
    cfg = SimpleNamespace(public_origin=ORIGIN, loanhub_origin="https://loanhub.example.test",
                          store=SimpleNamespace(resolve=lambda session: record if session == "session" else None),
                          verifier=SimpleNamespace(_public_key=object(), _company_id=COMPANY, _client=None))
    monkeypatch.setattr(routes, "_config", lambda request: cfg)

    def verifier(**kwargs):
        assert kwargs["allow_unverified_company_owner"] is False
        return SimpleNamespace(verify=lambda token: STAFF)

    monkeypatch.setattr(routes, "LoanHubStaffVerifier", verifier)

    def get(self, url, **kwargs):
        upstream.append(kwargs)
        return httpx.Response(200, json=[
            {"company_id": str(COMPANY), "id": str(BRANCH), "is_active": True}
        ])

    monkeypatch.setattr(httpx.Client, "get", get)

    def save(staff, branch, sample, action, **kwargs):
        calls.append((staff, branch, sample, action, kwargs))
        return 1, 2, SimpleNamespace(action=action, branch_id=branch.branch_id,
                                     recorded_at=datetime.now(timezone.utc))

    monkeypatch.setattr(store, "record", save)
    with TestClient(app, base_url=ORIGIN, cookies={COOKIE: "session", CSRF_COOKIE: "test-csrf"}) as client:
        yield app, client, calls, upstream


def post(client, action="clock-in", body=None, origin=ORIGIN, csrf="test-csrf"):
    return client.post(PATH + action, json=payload() if body is None else body,
                       headers={"Origin": origin, "x-csrf-token": csrf})


@pytest.mark.parametrize("action", ["clock-in", "clock-out"])
def test_disabled(configured, action):
    app, client, calls, upstream = configured
    app.state.staff_attendance_enabled = False
    assert post(client, action).status_code == 503
    assert calls == upstream == []


@pytest.mark.parametrize("action", ["clock-in", "clock-out"])
def test_authorized_write(configured, action):
    _, client, calls, upstream = configured
    response = post(client, action)
    assert response.status_code == 201
    assert response.json()["action"] == action.replace("-", "_")
    assert response.headers["cache-control"] == "no-store"
    assert len(calls) == len(upstream) == 1
    assert calls[0][0] == STAFF
    assert upstream[0]["headers"]["X-Active-Role"] == "loan_officer"


def test_denials_before_database(configured):
    _, client, calls, upstream = configured
    assert post(client, origin="https://other.example.test").status_code == 403
    assert post(client, csrf="bad").status_code == 403
    assert post(client, body=payload(branch_id=str(uuid4()))).status_code == 403
    assert post(client, body=payload(company_id=str(uuid4()))).status_code == 422
    assert post(client, body=payload(captured_at="2026-01-01T00:00:00")).status_code == 422
    client.cookies.clear()
    assert post(client).status_code == 401
    assert calls == upstream == []


def test_cross_company_directory(configured, monkeypatch):
    _, client, calls, _ = configured
    monkeypatch.setattr(httpx.Client, "get", lambda *args, **kw: httpx.Response(
        200, json=[{"company_id": str(uuid4()), "id": str(BRANCH), "is_active": True}]))
    assert post(client).status_code == 503
    assert calls == []


@pytest.mark.parametrize("code,status", [
    ("OUTSIDE_PERIMETER", 422), ("LOCATION_UNVERIFIED", 422),
    ("ALREADY_CLOCKED_IN", 409), ("NOT_CLOCKED_IN", 409),
])
def test_policy_errors(configured, monkeypatch, code, status):
    app, client, _, _ = configured
    def reject(*args, **kwargs):
        raise AttendanceRejected(code)
    monkeypatch.setattr(app.state.staff_attendance_store, "record", reject)
    response = post(client)
    assert response.status_code == status
    assert response.json()["code"] == code
