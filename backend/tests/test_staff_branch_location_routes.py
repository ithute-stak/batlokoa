from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app import staff_branch_location_routes as routes
from backend.app.staff_branch_location_store import BranchLocationStore
from backend.app.staff_authorization import VerifiedStaffIdentity
from backend.app.staff_login_routes import CSRF_COOKIE

ORIGIN = "https://batlokoa.example.test"
COMPANY = uuid4()
BRANCH = uuid4()
OWNER = VerifiedStaffIdentity(uuid4(), COMPANY, "COMPANY_OWNER", True,
                              frozenset(), True)
PATH = f"/api/v1/staff/manage/branches/{BRANCH}/location"


def payload(**changes):
    return dict(latitude=-29.31, longitude=27.48, accuracy_m=2.0,
                captured_at=datetime.now(timezone.utc).isoformat(),
                confirm=True) | changes


@pytest.fixture
def configured(monkeypatch):
    calls = []
    store = BranchLocationStore(lambda: pytest.fail("Unexpected database access"))
    monkeypatch.setattr(app.state, "staff_branch_location_enabled", True, raising=False)
    monkeypatch.setattr(app.state, "staff_branch_location_store", store, raising=False)
    monkeypatch.setattr(routes, "_config", lambda request: SimpleNamespace(public_origin=ORIGIN))
    monkeypatch.setattr(routes, "owner_context", lambda request, **kw: (
        SimpleNamespace(csrf_token="test-csrf", access_token="test-token"), OWNER, None))
    monkeypatch.setattr(routes, "call_loanhub", lambda *args, **kw: httpx.Response(200, json=[
        {"company_id": str(COMPANY), "id": str(BRANCH), "is_active": True}]))
    def register(*args, **kw):
        calls.append((args, kw))
        return 1, datetime.now(timezone.utc)
    monkeypatch.setattr(store, "register", register)
    with TestClient(app, base_url=ORIGIN, cookies={CSRF_COOKIE: "test-csrf"}) as client:
        yield client, calls


def post(client, body=None, origin=ORIGIN, csrf="test-csrf", path=PATH):
    return client.post(path, json=payload() if body is None else body,
                       headers={"Origin": origin, "x-csrf-token": csrf})


def test_disabled_by_default(monkeypatch):
    monkeypatch.setattr(app.state, "staff_branch_location_enabled", False, raising=False)
    with TestClient(app, base_url=ORIGIN) as client:
        assert post(client).status_code == 503


def test_valid_registration(configured):
    client, calls = configured
    response = post(client)
    assert response.status_code == 201
    assert response.json()["radius_m"] == 10
    assert response.headers["cache-control"] == "no-store"
    assert len(calls) == 1
    assert calls[0][0][0] == OWNER
    assert calls[0][0][1].branch_id == BRANCH


def test_wrong_origin_and_csrf(configured):
    client, calls = configured
    assert post(client, origin="https://other.example.test").status_code == 403
    assert post(client, csrf="incorrect").status_code == 403
    assert calls == []


def test_unverified_owner(configured, monkeypatch):
    client, calls = configured
    monkeypatch.setattr(routes, "owner_context", lambda request, **kw: (
        None, None, routes.fail("OWNER_VERIFICATION_REQUIRED", 403)))
    assert post(client).status_code == 403
    assert calls == []


@pytest.mark.parametrize("changes", [
    {"confirm": False}, {"accuracy_m": 6}, {"latitude": 91},
    {"company_id": str(uuid4())},
    {"captured_at": (datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat()},
    {"captured_at": (datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()},
])
def test_invalid_capture(configured, changes):
    client, calls = configured
    assert post(client, payload(**changes)).status_code == 422
    assert calls == []


def test_unknown_branch(configured):
    client, calls = configured
    assert post(client, path=f"/api/v1/staff/manage/branches/{uuid4()}/location").status_code == 403
    assert calls == []


def test_cross_company_directory(configured, monkeypatch):
    client, calls = configured
    monkeypatch.setattr(routes, "call_loanhub", lambda *args, **kw: httpx.Response(200, json=[
        {"company_id": str(uuid4()), "id": str(BRANCH), "is_active": True}]))
    assert post(client).status_code == 503
    assert calls == []
