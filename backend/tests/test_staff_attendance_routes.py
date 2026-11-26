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

    original_get = httpx.Client.get

    def get(self, url, **kwargs):
        if str(url) != cfg.loanhub_origin + "/api/v1/branches/?limit=100":
            return original_get(self, url, **kwargs)
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


@pytest.mark.parametrize("endpoint", ["status", "history"])
def test_reads_disabled_or_unauthenticated(configured, monkeypatch, endpoint):
    app, client, _, _ = configured
    monkeypatch.setattr(app.state.staff_attendance_store, "read_sessions",
                        lambda *a, **kw: pytest.fail("Unauthorized database read"))
    app.state.staff_attendance_enabled = False
    assert client.get(PATH + endpoint).status_code == 503
    app.state.staff_attendance_enabled = True
    client.cookies.clear()
    assert client.get(PATH + endpoint).status_code == 401


def test_status_empty_and_open(configured, monkeypatch):
    app, client, _, _ = configured
    rows = []
    def read(identity, **kwargs):
        assert identity == STAFF
        assert kwargs == dict(open_only=True, limit=1, before=None)
        return rows
    monkeypatch.setattr(app.state.staff_attendance_store, "read_sessions", read)
    assert client.get(PATH + "status").json() == {"clocked_in": False, "session": None}
    rows.append({"session_id": 1, "branch_id": str(BRANCH),
                 "clocked_in_at": "2026-11-26T05:00:00+00:00", "clocked_out_at": None})
    response = client.get(PATH + "status")
    assert response.json() == {"clocked_in": True, "session": rows[0]}
    assert response.headers["cache-control"] == "no-store"


def test_history_pagination_and_scope(configured, monkeypatch):
    app, client, _, _ = configured
    def read(identity, **kwargs):
        assert identity == STAFF
        assert kwargs == dict(open_only=False, limit=1, before=10)
        return [{"session_id": 9}]
    monkeypatch.setattr(app.state.staff_attendance_store, "read_sessions", read)
    response = client.get(PATH + "history", params={"limit": 1, "before": 10,
                         "employee_id": str(uuid4()), "company_id": str(uuid4())})
    assert response.status_code == 200
    assert response.json() == {"sessions": [{"session_id": 9}], "next_before": 9}


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "before=0", "before=9223372036854775808"])
def test_history_invalid_pagination(configured, monkeypatch, query):
    app, client, _, _ = configured
    monkeypatch.setattr(app.state.staff_attendance_store, "read_sessions",
                        lambda *a, **kw: pytest.fail("Invalid pagination reached storage"))
    assert client.get(PATH + "history?" + query).status_code == 422


@pytest.fixture
def monitoring(configured, monkeypatch):
    from backend.app.staff_attendance_monitor_store import AttendanceMonitorStore
    from backend.app.staff_attendance_monitor import MonitorState, MonitorAlert
    from backend.app.staff_geofence import LocationState
    app, client, _, upstream = configured
    store = AttendanceMonitorStore(lambda: pytest.fail("Unexpected database access"))
    app.state.staff_attendance_monitor_store = store
    calls = []
    def save(staff, branch, session_id, sample, **kwargs):
        calls.append((staff, branch, session_id, sample, kwargs))
        return (LocationState.OUTSIDE,
                MonitorState(datetime.now(timezone.utc), LocationState.OUTSIDE),
                MonitorAlert.EXIT)
    monkeypatch.setattr(store, "record", save)
    return app, client, calls, upstream


def test_monitor_disabled_by_default_and_independently_gated(monitoring):
    app, client, calls, upstream = monitoring
    assert post(client, "monitor", payload(session_id=7)).status_code == 503
    app.state.staff_attendance_monitor_enabled = True
    app.state.staff_attendance_enabled = False
    assert post(client, "monitor", payload(session_id=7)).status_code == 503
    assert calls == upstream == []


def test_monitor_authorized_response(monitoring):
    app, client, calls, upstream = monitoring
    app.state.staff_attendance_monitor_enabled = True
    response = post(client, "monitor", payload(session_id=7))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["session_id"] == 7
    assert data["reading"] == data["last_confirmed"] == "verified_outside"
    assert data["transition_recorded"] is True
    assert set(data) == {"session_id", "reading", "last_confirmed", "observed_at", "transition_recorded"}
    assert len(calls) == len(upstream) == 1
    assert calls[0][0] == STAFF and calls[0][1].branch_id == BRANCH
    assert calls[0][2] == 7
    assert upstream[0]["headers"]["X-Active-Role"] == "loan_officer"


def test_monitor_denials_before_storage(monitoring):
    app, client, calls, upstream = monitoring
    app.state.staff_attendance_monitor_enabled = True
    body = payload(session_id=7)
    assert post(client, "monitor", body, origin="https://other.example.test").status_code == 403
    assert post(client, "monitor", body, csrf="bad").status_code == 403
    assert post(client, "monitor", body | {"branch_id": str(uuid4())}).status_code == 403
    assert post(client, "monitor", body | {"employee_id": str(uuid4())}).status_code == 422
    assert post(client, "monitor", body | {"company_id": str(uuid4())}).status_code == 422
    client.cookies.clear()
    assert post(client, "monitor", body).status_code == 401
    assert calls == upstream == []


@pytest.mark.parametrize("session_id", [0, -1, True, "7", 9223372036854775808])
def test_monitor_invalid_session_id(monitoring, session_id):
    app, client, calls, upstream = monitoring
    app.state.staff_attendance_monitor_enabled = True
    assert post(client, "monitor", payload(session_id=session_id)).status_code == 422
    assert calls == upstream == []


@pytest.mark.parametrize("code,status", [
    ("NO_ACTIVE_SESSION", 409), ("LOCATION_REPLAYED", 409),
    ("LOCATION_UNVERIFIED", 422), ("BRANCH_LOCATION_UNAVAILABLE", 503),
])
def test_monitor_policy_errors(monitoring, monkeypatch, code, status):
    app, client, _, _ = monitoring
    app.state.staff_attendance_monitor_enabled = True
    def reject(*args, **kwargs):
        raise AttendanceRejected(code)
    monkeypatch.setattr(app.state.staff_attendance_monitor_store, "record", reject)
    response = post(client, "monitor", payload(session_id=7))
    assert response.status_code == status
    assert response.json()["code"] == (code if status != 503 else "MONITOR_UNAVAILABLE")


OWNER_ALERTS = "/api/v1/staff/manage/attendance/alerts"


@pytest.fixture
def owner_inbox(configured, monkeypatch):
    from backend.app import owner_staff_management_routes as owner_routes
    from backend.app.owner_attendance_inbox import OwnerAttendanceInbox
    app, client, _, _ = configured
    owner = VerifiedStaffIdentity(uuid4(), COMPANY, "COMPANY_OWNER", True,
                                  frozenset(), True)
    identity = [owner]
    calls = []
    monkeypatch.setattr(owner_routes, "_config", routes._config)

    def verifier(**kwargs):
        assert kwargs["allow_unverified_company_owner"] is False
        return SimpleNamespace(verify=lambda token: identity[0])

    monkeypatch.setattr(owner_routes, "LoanHubStaffVerifier", verifier)
    inbox = OwnerAttendanceInbox(lambda: pytest.fail("Unexpected database access"))
    app.state.owner_attendance_inbox = inbox

    def read(staff, **kwargs):
        calls.append((staff, kwargs))
        return {"alerts": [], "next_after": kwargs["after"], "has_more": False}

    monkeypatch.setattr(inbox, "read", read)
    return app, client, owner, identity, calls


def test_owner_inbox_disabled_by_default(owner_inbox):
    app, client, _, _, calls = owner_inbox
    assert client.get(OWNER_ALERTS).status_code == 503
    app.state.owner_attendance_inbox_enabled = True
    app.state.staff_attendance_enabled = False
    assert client.get(OWNER_ALERTS).status_code == 503
    assert calls == []


def test_owner_inbox_uses_verified_scope(owner_inbox):
    app, client, owner, _, calls = owner_inbox
    app.state.owner_attendance_inbox_enabled = True
    response = client.get(OWNER_ALERTS, params={
        "after": 5, "limit": 2, "company_id": str(uuid4())})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"alerts": [], "next_after": 5, "has_more": False}
    assert calls == [(owner, {"after": 5, "limit": 2})]


def test_owner_inbox_rejects_nonowners_and_cross_site(owner_inbox):
    app, client, owner, identity, calls = owner_inbox
    app.state.owner_attendance_inbox_enabled = True
    assert client.get(OWNER_ALERTS, headers={"Origin": "https://foreign.test"}).status_code == 403
    assert client.get(OWNER_ALERTS, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    identity[0] = STAFF
    assert client.get(OWNER_ALERTS).status_code == 403
    identity[0] = VerifiedStaffIdentity(owner.user_id, COMPANY, "COMPANY_ADMIN",
                                        True, frozenset(), True)
    assert client.get(OWNER_ALERTS).status_code == 403
    identity[0] = owner
    client.cookies.clear()
    assert client.get(OWNER_ALERTS).status_code == 401
    assert calls == []


@pytest.mark.parametrize("query", ["after=-1", "after=9223372036854775808",
                                    "limit=0", "limit=101"])
def test_owner_inbox_rejects_invalid_pagination(owner_inbox, query):
    app, client, _, _, calls = owner_inbox
    app.state.owner_attendance_inbox_enabled = True
    assert client.get(OWNER_ALERTS + "?" + query).status_code == 422
    assert calls == []


@pytest.mark.parametrize("role,active,wide", [
    ("COMPANY_ADMIN", True, True), ("LOAN_OFFICER", True, False),
    ("COMPANY_OWNER", False, True), ("COMPANY_OWNER", True, False),
])
def test_owner_inbox_storage_requires_active_owner(role, active, wide):
    from backend.app.owner_attendance_inbox import OwnerAttendanceInbox
    from backend.app.staff_authorization import StaffAccessDenied
    inbox = OwnerAttendanceInbox(lambda: pytest.fail("Unauthorized storage access"))
    identity = VerifiedStaffIdentity(uuid4(), COMPANY, role, active, frozenset(), wide)
    with pytest.raises(StaffAccessDenied):
        inbox.read(identity)


OWNER_ACCESS = "/api/v1/staff/manage/attendance/access-events"


@pytest.fixture
def access_inbox(owner_inbox, monkeypatch):
    app, client, owner, identity, calls = owner_inbox
    app.state.owner_attendance_inbox_enabled = True
    events = []
    def read(staff, **kwargs):
        calls.append((staff, kwargs))
        return {"events": events, "next_before": None, "has_more": False}
    monkeypatch.setattr(app.state.owner_attendance_inbox, "read_access_events", read)
    return app, client, owner, identity, calls, events


def test_access_inbox_independent_release_gate(access_inbox):
    app, client, _, _, calls, _ = access_inbox
    assert client.get(OWNER_ACCESS).status_code == 503
    app.state.owner_access_inbox_enabled = True
    app.state.owner_attendance_inbox_enabled = False
    assert client.get(OWNER_ACCESS).status_code == 503
    app.state.owner_attendance_inbox_enabled = True
    app.state.staff_attendance_enabled = False
    assert client.get(OWNER_ACCESS).status_code == 503
    assert calls == []


def test_access_inbox_verified_scope_and_cursor(access_inbox):
    app, client, owner, _, calls, _ = access_inbox
    app.state.owner_access_inbox_enabled = True
    at, event_id = datetime.now(timezone.utc), uuid4()
    response = client.get(OWNER_ACCESS, params={
        "before_at": at.isoformat(), "before_id": str(event_id), "limit": 2,
        "company_id": str(uuid4()), "employee_id": str(uuid4())})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"events": [], "next_before": None, "has_more": False}
    assert calls == [(owner, {"before_at": at, "before_id": event_id, "limit": 2})]


def test_access_inbox_rejects_nonowners_and_cross_site(access_inbox):
    app, client, owner, identity, calls, _ = access_inbox
    app.state.owner_access_inbox_enabled = True
    assert client.get(OWNER_ACCESS, headers={"Origin": "https://foreign.test"}).status_code == 403
    assert client.get(OWNER_ACCESS, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    identity[0] = STAFF
    assert client.get(OWNER_ACCESS).status_code == 403
    identity[0] = VerifiedStaffIdentity(owner.user_id, COMPANY, "COMPANY_ADMIN",
                                        True, frozenset(), True)
    assert client.get(OWNER_ACCESS).status_code == 403
    identity[0] = owner
    client.cookies.clear()
    assert client.get(OWNER_ACCESS).status_code == 401
    assert calls == []


@pytest.mark.parametrize("query", [
    "limit=0", "limit=101", "before_id=invalid",
    "before_at=2026-11-26T08:00:00Z",
    "before_id=12345678-1234-1234-1234-123456789abc",
    "before_at=2026-11-26T08:00:00&before_id=12345678-1234-1234-1234-123456789abc",
])
def test_access_inbox_invalid_cursor(access_inbox, query):
    app, client, _, _, calls, _ = access_inbox
    app.state.owner_access_inbox_enabled = True
    assert client.get(OWNER_ACCESS + "?" + query).status_code == 422
    assert calls == []


def test_access_inbox_enriches_names_without_guessing_branch(access_inbox, monkeypatch):
    app, client, owner, _, _, events = access_inbox
    app.state.owner_access_inbox_enabled = True
    events.append({"event_id": str(uuid4()), "employee_id": str(owner.user_id),
        "branch_id": None, "event_type": "staff_logged_out",
        "observed_at": datetime.now(timezone.utc).isoformat()})
    monkeypatch.setattr(routes, "_owner_alert_labels",
        lambda *args: ({owner.user_id: "Synthetic Employee"}, {}))
    response = client.get(OWNER_ACCESS)
    assert response.status_code == 200
    event = response.json()["events"][0]
    assert event["employee_name"] == "Synthetic Employee"
    assert event["branch_name"] is None
    assert event["branch_id"] is None


def test_access_inbox_directory_failure_omits_names(access_inbox, monkeypatch):
    app, client, owner, _, _, events = access_inbox
    app.state.owner_access_inbox_enabled = True
    events.append({"event_id": str(uuid4()), "employee_id": str(owner.user_id),
        "branch_id": str(BRANCH), "event_type": "reported_login_outside",
        "observed_at": datetime.now(timezone.utc).isoformat()})
    def unavailable(*args):
        raise ValueError("Synthetic directory failure")
    monkeypatch.setattr(routes, "_owner_alert_labels", unavailable)
    response = client.get(OWNER_ACCESS)
    assert response.status_code == 200
    event = response.json()["events"][0]
    assert event["employee_name"] is None and event["branch_name"] is None
