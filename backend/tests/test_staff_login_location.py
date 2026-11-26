"""Login location boundary regression tests with synthetic staff and transport."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from backend.app import staff_login_routes as routes
from backend.app.staff_attendance_access_store import AttendanceAccessStore
from backend.app.staff_authorization import VerifiedStaffIdentity
from backend.app.staff_geofence import LocationState


@pytest.fixture
def context(monkeypatch):
    company, branch = uuid4(), uuid4()
    identity = VerifiedStaffIdentity(uuid4(), company, "LOAN_OFFICER",
                                     True, frozenset({branch}))
    state = SimpleNamespace(identity=identity, calls=[], reads=[], active=True,
                            directory_company=company)
    class Verifier:
        def __init__(self, **kwargs):
            assert kwargs["allow_unverified_company_owner"] is False
        def verify(self, token):
            assert token == "synthetic-token"
            return state.identity
    class Store(AttendanceAccessStore):
        def record_login(self, identity, event_id, branch, sample, *, captured_at):
            state.calls.append((identity, event_id, branch, sample, captured_at))
            return LocationState.OUTSIDE, True
    def handler(request):
        state.reads.append(request)
        assert request.headers["Authorization"] == "Bearer synthetic-token"
        assert request.headers["X-Company-ID"] == str(company)
        return httpx.Response(200, json=[{"id": str(branch),
            "company_id": str(state.directory_company), "is_active": state.active}])
    monkeypatch.setattr(routes, "LoanHubStaffVerifier", Verifier)
    app_state = SimpleNamespace(staff_attendance_enabled=True,
        staff_login_location_enabled=True, staff_attendance_access_store=Store(None))
    request = SimpleNamespace(app=SimpleNamespace(state=app_state))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        cfg = SimpleNamespace(loanhub_origin="https://loanhub.example.test",
            verifier=SimpleNamespace(_public_key=object(), _company_id=company, _client=None),
            client=client)
        location = routes.LoginLocation(latitude=-29.31, longitude=27.48,
            accuracy_m=2.0, captured_at=datetime.now(timezone.utc))
        yield state, request, cfg, location, branch


def test_resolves_branch_from_verified_membership(context):
    state, request, cfg, location, branch = context
    assert location.branch_id is None
    assert routes._login_location(request, cfg, "synthetic-token", location) == "verified_outside"
    assert len(state.calls) == len(state.reads) == 1
    assert state.calls[0][2].branch_id == branch
    assert state.calls[0][0] == state.identity


@pytest.mark.parametrize("scenario", ["mismatch", "ambiguous", "no_branch",
    "inactive", "foreign_directory", "missing_capture", "disabled"])
def test_uncertain_or_unauthorized_location_never_records_event(context, scenario):
    state, request, cfg, location, branch = context
    if scenario == "mismatch":
        location = location.model_copy(update={"branch_id": uuid4()})
    elif scenario in {"ambiguous", "no_branch"}:
        from dataclasses import replace
        state.identity = replace(state.identity,
            branch_ids=frozenset({branch, uuid4()}) if scenario == "ambiguous" else frozenset())
    elif scenario == "inactive":
        state.active = False
    elif scenario == "foreign_directory":
        state.directory_company = uuid4()
    elif scenario == "missing_capture":
        location = None
    else:
        request.app.state.staff_login_location_enabled = False
    result = routes._login_location(request, cfg, "synthetic-token", location)
    assert result == (None if scenario == "disabled" else "unverified")
    assert not state.calls
    if scenario not in {"inactive", "foreign_directory"}:
        assert not state.reads
