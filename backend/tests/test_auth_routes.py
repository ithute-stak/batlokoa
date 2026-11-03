"""Opt-in OIDC browser route tests using fake IdP and session store.

No live authorisation is configured or exercised.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from backend.app.auth_routes import AuthRouteConfig
from backend.app.auth_verification import CentralAccessClaims
from backend.app.main import app
from backend.app.oidc_login import (
    ExchangedTokens, LoginDenied, LoginUnavailable,
    OidcLoginService,
)
from backend.app.sessions import ActiveSession, SessionGrant
from backend.app.identity import CustomerContext

ISSUER = "https://auth.example.test"
ORIGIN = "https://testserver"
SUBJECT = str(uuid4())
SID = str(uuid4())
TENANT = UUID("d921126e-e1a7-482e-ad1b-6e99b1682e19")


class Transactions:
    def __init__(self):
        self.by_state = {}
        self.calls = 0

    async def save(self, transaction, *, expires_seconds):
        assert expires_seconds <= 300
        self.by_state[transaction.state] = transaction

    async def consume(self, *, state):
        self.calls += 1
        return self.by_state.pop(state, None)


class Exchange:
    def __init__(self):
        self.calls = []

    async def exchange(self, *, code, code_verifier, redirect_uri):
        self.calls.append((code, code_verifier, redirect_uri))
        return ExchangedTokens("signed-access-token", "signed-id-token")


class AccessVerifier:
    issuer = ISSUER
    audience = "batlokoa"

    def verify(self, token):
        assert token == "signed-access-token"
        now = datetime.now(timezone.utc)
        return CentralAccessClaims(
            iss=ISSUER, aud="batlokoa", sub=SUBJECT, sid=SID,
            iat=int(now.timestamp()), nbf=int(now.timestamp()),
            exp=int((now + timedelta(minutes=4)).timestamp()),
            token_use="access",
        )


class IdVerifier:
    def __init__(self):
        self.expected_nonce = None
        self.reject = False

    def verify(self, id_token, *, expected_nonce, expected_subject):
        assert id_token == "signed-id-token"
        assert expected_subject == SUBJECT
        self.expected_nonce = expected_nonce
        if self.reject:
            raise ValueError("Nonce mismatch")


class Sessions:
    def __init__(self):
        self.issued = []
        self.revoked = set()
        self.csrf = "safe-csrf-token-of-sufficient-length"
        self.session = "opaque-session-token-of-sufficient-length"

    async def issue(self, *, claims, tenant_id, ttl_seconds=900):
        assert claims.sub == SUBJECT
        assert tenant_id == TENANT
        self.issued.append(claims)
        return SessionGrant(self.session, self.csrf,
                            datetime.now(timezone.utc) + timedelta(minutes=4))

    async def resolve(self, token, *, csrf_token=None, require_csrf=False):
        if (token != self.session or token in self.revoked or not self.issued
                or require_csrf and csrf_token != self.csrf):
            return None
        return ActiveSession(
            CustomerContext(str(TENANT), str(uuid4()), SUBJECT), UUID(SID)
        )

    async def revoke(self, token):
        self.revoked.add(token)
        return True


@pytest.fixture(autouse=True)
def clean_config():
    if hasattr(app.state, "auth_route_config"):
        del app.state.auth_route_config
    yield
    if hasattr(app.state, "auth_route_config"):
        del app.state.auth_route_config


def setup():
    transactions, exchange, id_verifier, sessions = (
        Transactions(), Exchange(), IdVerifier(), Sessions()
    )
    service = OidcLoginService(
        issuer=ISSUER, authorization_endpoint=ISSUER + "/authorize",
        token_endpoint=ISSUER + "/token", client_id="batlokoa",
        redirect_uri=ORIGIN + "/api/v1/auth/callback",
        tenant_id=TENANT, verifier=AccessVerifier(),
        transactions=transactions, exchanger=exchange,
        id_token_verifier=id_verifier, sessions=sessions,
    )
    app.state.auth_route_config = AuthRouteConfig(service, sessions, ORIGIN)
    return transactions, exchange, id_verifier, sessions


def test_default_disabled_all_auth_routes():
    client = TestClient(app, base_url=ORIGIN, follow_redirects=False)
    assert client.get("/api/v1/auth/login").status_code == 503
    assert client.get("/api/v1/auth/callback").status_code == 503
    assert client.get("/api/v1/auth/session").status_code == 503
    assert client.post("/api/v1/auth/logout").status_code == 503


def test_pkce_login_uses_one_time_state_nonce_and_http_only_cookies():
    tx, exchanger, idv, sessions = setup()
    client = TestClient(app, base_url=ORIGIN, follow_redirects=False)
    start = client.get("/api/v1/auth/login")
    assert start.status_code == 303
    q = parse_qs(urlsplit(start.headers["location"]).query)
    assert q["response_type"] == ["code"]
    assert q["code_challenge_method"] == ["S256"]
    assert len(q["code_challenge"][0]) >= 40
    assert q["redirect_uri"] == [ORIGIN + "/api/v1/auth/callback"]
    assert q["scope"] == ["openid"]
    assert "HttpOnly" in start.headers["set-cookie"]
    assert "SameSite=lax" in start.headers["set-cookie"]
    assert "no-store" in start.headers["cache-control"]
    state = q["state"][0]
    assert state in tx.by_state
    assert q["nonce"][0] == tx.by_state[state].nonce
    result = client.get("/api/v1/auth/callback", params={"state": state, "code": "authorization-code"})
    assert result.status_code == 303
    assert result.headers["location"] == ORIGIN + "/"
    assert "HttpOnly" in result.headers["set-cookie"]
    assert len(sessions.issued) == 1
    assert idv.expected_nonce == q["nonce"][0]
    assert len(exchanger.calls) == 1
    assert exchanger.calls[0][0] == "authorization-code"
    assert client.get("/api/v1/auth/session").json() == {"authenticated": True}
    replay = client.get("/api/v1/auth/callback", params={"state": state, "code": "authorization-code"})
    assert replay.status_code == 401
    assert len(sessions.issued) == 1
    assert len(exchanger.calls) == 1


def test_mismatched_state_never_reaches_token_exchanger():
    tx, exchanger, _, sessions = setup()
    client = TestClient(app, base_url=ORIGIN, follow_redirects=False)
    start = client.get("/api/v1/auth/login")
    q = parse_qs(urlsplit(start.headers["location"]).query)
    bad = client.get("/api/v1/auth/callback", params={"state": "unrelated", "code": "code"})
    assert bad.status_code == 401
    assert exchanger.calls == []
    assert sessions.issued == []


def test_id_token_nonce_failure_never_issues_session():
    tx, exchanger, idv, sessions = setup()
    idv.reject = True
    client = TestClient(app, base_url=ORIGIN, follow_redirects=False)
    start = client.get("/api/v1/auth/login")
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    response = client.get("/api/v1/auth/callback", params={"state": state, "code": "code"})
    assert response.status_code == 401
    assert len(exchanger.calls) == 1
    assert sessions.issued == []
    assert client.get("/api/v1/auth/session").json() == {"authenticated": False}


def test_logout_requires_correct_origin_and_double_submit_csrf():
    _, _, _, sessions = setup()
    client = TestClient(app, base_url=ORIGIN, follow_redirects=False)
    start = client.get("/api/v1/auth/login")
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    client.get("/api/v1/auth/callback", params={"state": state, "code": "code"})
    assert client.post("/api/v1/auth/logout", headers={
        "Origin": "https://attacker.example", "X-CSRF-Token": sessions.csrf
    }).status_code == 403
    assert client.post("/api/v1/auth/logout", headers={
        "Origin": ORIGIN, "X-CSRF-Token": "invalid"
    }).status_code == 403
    assert client.post("/api/v1/auth/logout", headers={
        "Origin": ORIGIN, "X-CSRF-Token": sessions.csrf
    }).status_code == 200
    assert client.get("/api/v1/auth/session").json() == {"authenticated": False}


def test_rejects_untrusted_endpoint_and_callback():
    with pytest.raises(ValueError):
        OidcLoginService(
            issuer=ISSUER, authorization_endpoint="https://unknown.test/authorize",
            token_endpoint=ISSUER + "/token", client_id="batlokoa",
            redirect_uri=ORIGIN + "/api/v1/auth/callback",
            tenant_id=TENANT, verifier=AccessVerifier(),
            transactions=Transactions(), exchanger=Exchange(),
            id_token_verifier=IdVerifier(), sessions=Sessions(),
        )
