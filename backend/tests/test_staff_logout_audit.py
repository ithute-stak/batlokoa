"""Logout security regression tests using synthetic sessions, no live services."""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.app import staff_login_routes as routes
from backend.app.staff_attendance_access_store import AttendanceAccessStore
from backend.app.staff_authorization import VerifiedStaffIdentity


@pytest.fixture
def context(monkeypatch):
    branch, company = uuid4(), uuid4()
    identity = VerifiedStaffIdentity(uuid4(), company, "LOAN_OFFICER",
                                    True, frozenset({branch}))
    sessions = routes.StagingStaffSessionStore()
    session, csrf = sessions.issue("synthetic-token", 300)
    event_id = sessions.resolve(session).logout_event_id
    state = SimpleNamespace(calls=[], fail=False, verify_fail=False)
    class Verifier:
        def __init__(self, **kwargs):
            assert kwargs["allow_unverified_company_owner"] is False
        def verify(self, token):
            assert token == "synthetic-token"
            if state.verify_fail:
                raise routes.StaffVerificationUnavailable("synthetic failure")
            return identity
    class Audit(AttendanceAccessStore):
        def record_logout(self, actual_identity, actual_event):
            assert sessions.resolve(session) is None
            state.calls.append((actual_identity, actual_event))
            if state.fail:
                raise RuntimeError("synthetic database failure")
            return True
    monkeypatch.setattr(routes, "LoanHubStaffVerifier", Verifier)
    cfg = SimpleNamespace(public_origin="https://staff.example.test",
        loanhub_origin="https://loanhub.example.test", store=sessions,
        verifier=SimpleNamespace(_public_key=object(), _company_id=company, _client=None))
    monkeypatch.setattr(routes, "_config", lambda request: cfg)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(
            staff_attendance_enabled=True, staff_logout_audit_enabled=True,
            staff_attendance_access_store=Audit(None))),
        cookies={routes.COOKIE: session, routes.CSRF_COOKIE: csrf},
        headers={"origin": cfg.public_origin, "x-csrf-token": csrf})
    return state, request, sessions, session, identity, event_id


def test_logout_revokes_then_records_once(context):
    state, request, sessions, session, identity, event_id = context
    response = routes.staff_logout(request)
    assert response.status_code == 200
    assert sessions.resolve(session) is None
    assert state.calls == [(identity, event_id)]
    assert routes.staff_logout(request).status_code == 403
    assert state.calls == [(identity, event_id)]
    assert response.headers["cache-control"] == "no-store"
    assert len(response.headers.getlist("set-cookie")) == 2


@pytest.mark.parametrize("scenario", ["origin", "csrf_header", "csrf_cookie", "missing_session"])
def test_unauthorized_logout_cannot_record_or_revoke(context, scenario):
    state, request, sessions, session, _, _ = context
    if scenario == "origin":
        request.headers["origin"] = "https://other.example.test"
    elif scenario == "csrf_header":
        request.headers.pop("x-csrf-token")
    elif scenario == "csrf_cookie":
        request.cookies[routes.CSRF_COOKIE] = "invalid"
    else:
        request.cookies.pop(routes.COOKIE)
    assert routes.staff_logout(request).status_code == 403
    assert sessions.resolve(session) is not None
    assert not state.calls


@pytest.mark.parametrize("scenario", ["database_failure", "verification_failure",
    "attendance_disabled", "audit_disabled"])
def test_logout_completes_without_available_audit(context, scenario):
    state, request, sessions, session, identity, event_id = context
    if scenario == "database_failure":
        state.fail = True
    elif scenario == "verification_failure":
        state.verify_fail = True
    elif scenario == "attendance_disabled":
        request.app.state.staff_attendance_enabled = False
    else:
        request.app.state.staff_logout_audit_enabled = False
    assert routes.staff_logout(request).status_code == 200
    assert sessions.resolve(session) is None
    assert state.calls == ([(identity, event_id)] if state.fail else [])


def test_logout_ids_are_distinct_from_session_secrets():
    sessions = routes.StagingStaffSessionStore()
    a, _ = sessions.issue("synthetic-token", 300)
    b, _ = sessions.issue("synthetic-token", 300)
    assert sessions.resolve(a).logout_event_id != sessions.resolve(b).logout_event_id
    assert str(sessions.resolve(a).logout_event_id) != a
