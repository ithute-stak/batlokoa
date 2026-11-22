"""Company owner employee-management boundary tests.

All records and credentials are synthetic; no production user is modified.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app import owner_staff_management_routes as routes
from backend.app.loanhub_staff_verifier import LoanHubStaffVerifier
from backend.app.staff_login_routes import (
    COOKIE, CSRF_COOKIE, StaffLoginConfig, StagingStaffSessionStore,
)

ORIGIN = "https://batlokoa-owner-tests.example"
LOANHUB = "https://loanhub-owner-tests.example"
COMPANY = uuid4()
OWNER = uuid4()
BRANCH = uuid4()
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def bearer():
    return jwt.encode({
        "user_id": str(OWNER), "token_type": "access",
        "session_jti": "owner-reg-test",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }, KEY, algorithm="RS256")


@pytest.fixture
def setup_owner():
    verified = {"value": False}
    role = {"value": "company_owner"}

    def reply(req):
        assert req.url.path == "/api/v1/auth/me"
        return httpx.Response(200, json={
            "id": str(OWNER), "is_active": True,
            "is_verified": verified["value"],
            "must_change_password": False,
            "role": role["value"],
            "memberships": [{
                "company_id": str(COMPANY),
                "branch_id": None,
                "role": role["value"],
                "is_active": True,
            }],
        })
    with httpx.Client(transport=httpx.MockTransport(reply)) as upstream:
        verifier = LoanHubStaffVerifier(
            origin=LOANHUB, public_key=KEY.public_key(),
            batlokoa_company_id=COMPANY, client=upstream,
            allow_unverified_company_owner=True,
        )
        store = StagingStaffSessionStore()
        sid, csrf = store.issue(bearer(), 600)
        app.state.staff_login_config = StaffLoginConfig(
            public_origin=ORIGIN, loanhub_origin=LOANHUB,
            verifier=verifier, store=store, client=upstream,
        )
        app.state.staff_account_creation_enabled = False
        try:
            with TestClient(app, base_url=ORIGIN) as client:
                client.cookies.set(COOKIE, sid)
                client.cookies.set(CSRF_COOKIE, csrf)
                yield client, csrf, verified, role
        finally:
            del app.state.staff_login_config
            del app.state.staff_account_creation_enabled


def draft():
    return {
        "first_name": "Synthetic", "last_name": "Employee",
        "phone": "59000000", "password": "Synthetic-Not-Real-123",
        "role": "LOAN_OFFICER", "branch_id": str(BRANCH),
        "confirm": True,
    }


def test_employee_creation_is_disabled_by_default(setup_owner):
    client, csrf, verified, role = setup_owner
    response = client.post("/api/v1/staff/manage/members",
        headers={"Origin": ORIGIN, "x-csrf-token": csrf}, json=draft())
    assert response.status_code == 503
    assert response.json()["code"] == "STAFF_CREATION_NOT_RELEASED"


def test_read_only_owner_can_list_minimal_staff_and_branches(setup_owner, monkeypatch):
    client, _, verified, role = setup_owner
    calls = []
    def fake_call(request, *, method, path, token, company_id, json_body=None):
        calls.append((method, path, company_id))
        if path.startswith("/api/v1/branches"):
            return httpx.Response(200, json=[
                {"id": str(BRANCH), "company_id": str(COMPANY),
                 "name": "Maseru", "is_active": True},
            ])
        return httpx.Response(200, json=[{
            "id": str(uuid4()), "company_id": str(COMPANY),
            "branch_id": str(BRANCH), "role": "loan_officer",
            "is_active": True,
            "user": {"is_verified": False, "phone": "PRIVATE_PHONE",
                     "person": {"first_name": "Synthetic", "last_name": "Worker"}},
        }])
    monkeypatch.setattr(routes, "call_loanhub", fake_call)
    branches = client.get("/api/v1/staff/manage/branches")
    members = client.get("/api/v1/staff/manage/members")
    assert branches.status_code == 200
    assert members.status_code == 200
    assert branches.json()["branches"][0]["name"] == "Maseru"
    assert members.json()["members"][0]["verified"] is False
    assert "PRIVATE_PHONE" not in members.text
    assert len(calls) == 2
    assert all(row[2] == COMPANY for row in calls)


def test_owner_write_requires_verified_account_and_csrf(setup_owner, monkeypatch):
    client, csrf, verified, role = setup_owner
    app.state.staff_account_creation_enabled = True
    calls = []
    def fake_call(request, *, method, path, token, company_id, json_body=None):
        calls.append((method, path, json_body))
        return httpx.Response(201, json={
            "id": str(uuid4()), "company_id": str(COMPANY),
        })
    monkeypatch.setattr(routes, "call_loanhub", fake_call)
    headers = {"Origin": ORIGIN, "x-csrf-token": csrf}

    unverified = client.post("/api/v1/staff/manage/members",
        headers=headers, json=draft())
    assert unverified.status_code == 403
    assert unverified.json()["code"] == "OWNER_VERIFICATION_REQUIRED"
    assert calls == []

    verified["value"] = True
    forged = client.post("/api/v1/staff/manage/members",
        headers={"Origin": "https://foreign.example", "x-csrf-token": csrf},
        json=draft())
    assert forged.status_code == 403
    missing_csrf = client.post("/api/v1/staff/manage/members",
        headers={"Origin": ORIGIN}, json=draft())
    assert missing_csrf.status_code == 403
    owner_role = dict(draft(), role="COMPANY_OWNER", branch_id=None)
    denied = client.post("/api/v1/staff/manage/members",
        headers=headers, json=owner_role)
    assert denied.status_code == 422
    assert calls == []

    accepted = client.post("/api/v1/staff/manage/members",
        headers=headers, json=draft())
    assert accepted.status_code == 201
    assert accepted.json()["created"] is True
    assert accepted.json()["requires_verification"] is True
    assert len(calls) == 1
    assert calls[0][1] == "/api/v1/company-staff/accounts"
    assert calls[0][2]["role"] == "loan_officer"
    assert calls[0][2]["branch_id"] == str(BRANCH)
    assert "password" not in accepted.text


def test_cross_company_staff_records_fail_closed(setup_owner, monkeypatch):
    client, _, _, _ = setup_owner
    def wrong_company(request, *, method, path, token, company_id, json_body=None):
        return httpx.Response(200, json=[{
            "id": str(uuid4()), "name": "Wrong Company",
            "company_id": str(uuid4()), "is_active": True,
        }])
    monkeypatch.setattr(routes, "call_loanhub", wrong_company)
    assert client.get("/api/v1/staff/manage/branches").status_code == 503
    assert client.get("/api/v1/staff/manage/members").status_code == 503
