"""Phase 56: network-free staging BFF login and logout behavior."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.loanhub_staff_verifier import LoanHubStaffVerifier
from backend.app.staff_login_routes import StaffLoginConfig, StagingStaffSessionStore

COMPANY, BRANCH, USER = (uuid4() for _ in range(3))
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_access():
    return jwt.encode({
        "user_id": str(USER), "token_type": "access",
        "session_jti": "test-jti",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }, KEY, algorithm="RS256")


def test_routes_are_disabled_by_default():
    with TestClient(app, base_url="https://batlokoa.example") as client:
        assert client.get("/api/v1/staff/session").status_code == 503
        assert client.post("/api/v1/staff/login", json={
            "phone": "59000000", "password": "examplepassword",
        }, headers={"origin": "https://batlokoa.example"}).status_code == 503


def test_login_session_logout_and_reverification():
    access = make_access()
    observed = []

    def respond(req):
        observed.append(req)
        if req.url.path == "/api/v1/auth/login":
            assert req.method == "POST"
            return httpx.Response(200, json={
                "access_token": access, "token_type": "bearer",
            })
        if req.url.path == "/api/v1/auth/me":
            return httpx.Response(200, json={
                "id": str(USER), "role": "loan_officer", "is_active": True,
                "is_verified": True, "must_change_password": False,
                "memberships": [{
                    "company_id": str(COMPANY), "branch_id": str(BRANCH),
                    "role": "loan_officer", "is_active": True,
                }],
            })
        raise AssertionError("Unexpected LoanHub request")

    with httpx.Client(transport=httpx.MockTransport(respond)) as upstream:
        verifier = LoanHubStaffVerifier(
            origin="https://loanhub.example", public_key=KEY.public_key(),
            batlokoa_company_id=COMPANY, client=upstream,
        )
        app.state.staff_login_config = StaffLoginConfig(
            public_origin="https://batlokoa.example",
            loanhub_origin="https://loanhub.example",
            verifier=verifier, store=StagingStaffSessionStore(), client=upstream,
        )
        try:
            with TestClient(app, base_url="https://batlokoa.example") as browser:
                bad = browser.post("/api/v1/staff/login",
                                   json={"phone": "59000000", "password": "examplepassword"},
                                   headers={"origin": "https://evil.example"})
                assert bad.status_code == 403
                assert observed == []
                result = browser.post("/api/v1/staff/login", json={
                    "phone": "59000000", "password": "examplepassword",
                }, headers={"origin": "https://batlokoa.example"})
                assert result.status_code == 200
                assert "access_token" not in result.text
                assert result.json()["role"] == "LOAN_OFFICER"
                assert "HttpOnly" in result.headers["set-cookie"]
                active = browser.get("/api/v1/staff/session")
                assert active.status_code == 200
                assert active.json()["branch_ids"] == [str(BRANCH)]
                assert len([r for r in observed if r.url.path == "/api/v1/auth/me"]) >= 2
                assert browser.post("/api/v1/staff/logout",
                                    headers={"origin": "https://batlokoa.example"}).status_code == 403
                csrf = browser.cookies.get("__Host-batlokoa_staff_csrf")
                done = browser.post("/api/v1/staff/logout", headers={
                    "origin": "https://batlokoa.example",
                    "x-csrf-token": csrf,
                })
                assert done.status_code == 200
                assert browser.get("/api/v1/staff/session").status_code == 401
        finally:
            del app.state.staff_login_config
