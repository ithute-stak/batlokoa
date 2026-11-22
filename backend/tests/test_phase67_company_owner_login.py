"""Company owner must use verified LoanHub credentials and receive company-wide scope.

Network-free tests never access a real employee password or production records.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.loanhub_staff_verifier import LoanHubStaffVerifier
from backend.app.staff_login_routes import StaffLoginConfig, StagingStaffSessionStore

PUBLIC = "https://batlokoa-test.example"
LOANHUB = "https://loanhub-test.example"
COMPANY = uuid4()
USER = uuid4()
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def access_token():
    return jwt.encode({
        "user_id": str(USER),
        "token_type": "access",
        "session_jti": "owner-test-session",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }, KEY, algorithm="RS256")


@pytest.mark.parametrize(
    "verified, membership_company, active_membership, expected",
    [
        (True, COMPANY, True, 200),
        (False, COMPANY, True, 401),
        (True, uuid4(), True, 401),
        (True, COMPANY, False, 401),
    ],
)
def test_owner_login_needs_verified_active_batlokoa_membership(
    verified, membership_company, active_membership, expected,
):
    upstream_paths = []
    def upstream(req):
        upstream_paths.append(req.url.path)
        if req.url.path == "/api/v1/auth/login":
            return httpx.Response(200, json={
                "token_type": "bearer", "access_token": access_token(),
            })
        assert req.url.path == "/api/v1/auth/me"
        return httpx.Response(200, json={
            "id": str(USER),
            "role": "company_owner",
            "is_active": True,
            "is_verified": verified,
            "must_change_password": False,
            "memberships": [{
                "company_id": str(membership_company),
                "branch_id": None,
                "role": "company_owner",
                "is_active": active_membership,
            }],
        })
    with httpx.Client(transport=httpx.MockTransport(upstream)) as upstream_client:
        verifier = LoanHubStaffVerifier(
            origin=LOANHUB,
            public_key=KEY.public_key(),
            batlokoa_company_id=COMPANY,
            client=upstream_client,
        )
        app.state.staff_login_config = StaffLoginConfig(
            public_origin=PUBLIC, loanhub_origin=LOANHUB,
            verifier=verifier, store=StagingStaffSessionStore(),
            client=upstream_client,
        )
        try:
            with TestClient(app, base_url=PUBLIC) as browser:
                login = browser.post(
                    "/api/v1/staff/login",
                    headers={"Origin": PUBLIC},
                    json={"phone": "59000000", "password": "synthetic-password"},
                )
                assert login.status_code == expected
                assert "access_token" not in login.text
                assert "synthetic-password" not in login.text
                if expected == 200:
                    assert login.json()["company_wide_scope"] is True
                    session = browser.get("/api/v1/staff/session")
                    assert session.status_code == 200
                    data = session.json()
                    assert data["authenticated"] is True
                    assert data["role"] == "COMPANY_OWNER"
                    assert data["company_id"] == str(COMPANY)
                    assert data["company_wide_scope"] is True
                    assert data["branch_ids"] == []
                    assert browser.cookies.get("__Host-batlokoa_staff_session")
                else:
                    assert browser.get("/api/v1/staff/session").status_code == 401
                assert "/api/v1/auth/login" in upstream_paths
                assert "/api/v1/auth/me" in upstream_paths
        finally:
            del app.state.staff_login_config


def test_owner_role_is_not_accepted_from_browser_claims():
    with TestClient(app, base_url=PUBLIC) as browser:
        response = browser.get("/api/v1/staff/session", headers={
            "X-Active-Role": "company_owner",
            "X-Company-ID": str(COMPANY),
        })
        assert response.status_code == 503
