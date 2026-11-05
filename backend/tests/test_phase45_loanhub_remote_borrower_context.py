"""Phase 45: LoanHub-owned remote proof replaces direct LoanHub DB access."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.app.loanhub_identity_verifier import LoanHubIdentityVerifier
from backend.app.loanhub_remote_borrower_context import LoanHubRemoteBorrowerContext

USER = "72de5a5b-ad44-4eea-b871-81479fe7b045"
TENANT = "d921126e-e1a7-482e-ad1b-6e99b1682e19"
BORROWER = "cb6700f8-1808-46ca-bfc2-f030ad0e2d7c"
OTHER_TENANT = "9ff995dc-ad87-4a91-8a8f-18ddfc85d991"
OTHER_BORROWER = "9ff995dc-ad87-4a91-8a8f-18ddfc85d992"


def setup(*, role="borrower", context=None, context_code=200):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = jwt.encode({
        "user_id": USER,
        "token_type": "access",
        "session_jti": str(uuid4()),
        "session_version": 1,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }, key, algorithm="RS256")
    context = {
        "user_id": USER,
        "company_id": TENANT,
        "borrower_id": BORROWER,
        "role": "borrower",
        "session_active": True,
        "account_active": True,
    } if context is None else context
    requests = []

    def handle(request):
        requests.append(request)
        assert request.url.host == "loanhub.example.test"
        assert request.headers.get("authorization") == "Bearer " + token
        assert request.headers.get("cache-control") == "no-store"
        if request.url.path == "/api/v1/auth/me":
            return httpx.Response(200, json={
                "id": USER, "role": role, "is_active": True,
                "is_verified": True, "must_change_password": False,
            })
        if request.url.path == "/api/v1/auth/borrower-context":
            assert request.url.params["company_id"] == TENANT
            return httpx.Response(context_code, json=context)
        raise AssertionError("No other HTTP endpoint allowed")

    client = httpx.Client(transport=httpx.MockTransport(handle))
    mapping = LoanHubRemoteBorrowerContext(
        base_url="https://loanhub.example.test", client=client,
    )
    verifier = LoanHubIdentityVerifier(
        base_url="https://loanhub.example.test",
        public_key=key.public_key(),
        resolve_remote_borrower_context=mapping,
        client=client,
    )
    return verifier, client, requests, token


def test_verified_remote_user_and_company_ownership_success():
    verify, client, requests, token = setup()
    try:
        evidence = verify(token, TENANT, BORROWER)
        assert evidence is not None and evidence.session_active
        assert evidence.tenant_id == TENANT and evidence.borrower_id == BORROWER
        assert [r.url.path for r in requests] == [
            "/api/v1/auth/me", "/api/v1/auth/borrower-context",
        ]
    finally:
        client.close()


@pytest.mark.parametrize("context", [
    {"user_id": USER, "company_id": OTHER_TENANT, "borrower_id": BORROWER,
     "role": "borrower", "session_active": True, "account_active": True},
    {"user_id": USER, "company_id": TENANT, "borrower_id": OTHER_BORROWER,
     "role": "borrower", "session_active": True, "account_active": True},
    {"user_id": str(uuid4()), "company_id": TENANT, "borrower_id": BORROWER,
     "role": "borrower", "session_active": True, "account_active": True},
    {"user_id": USER, "company_id": TENANT, "borrower_id": BORROWER,
     "role": "superadmin", "session_active": True, "account_active": True},
    {"user_id": USER, "company_id": TENANT, "borrower_id": BORROWER,
     "role": "borrower", "session_active": False, "account_active": True},
    {"user_id": USER, "company_id": TENANT, "borrower_id": BORROWER,
     "role": "borrower", "session_active": True, "account_active": False},
    {"user_id": USER, "company_id": TENANT, "borrower_id": "INVALID",
     "role": "borrower", "session_active": True, "account_active": True},
    {},
])
def test_remote_proof_must_match_exact_verified_identity(context):
    verify, client, requests, token = setup(context=context)
    try:
        assert verify(token, TENANT, BORROWER) is None
        assert len(requests) == 2
    finally:
        client.close()


@pytest.mark.parametrize("status", [301, 302, 401, 403, 404, 429, 500, 503])
def test_remote_failure_does_not_fall_back_to_database_or_admin(status):
    verify, client, requests, token = setup(context_code=status)
    try:
        assert verify(token, TENANT, BORROWER) is None
        assert len(requests) == 2
    finally:
        client.close()


def test_admin_role_blocks_remote_context_request():
    verify, client, requests, token = setup(role="superadmin")
    try:
        assert verify(token, TENANT, BORROWER) is None
        assert [r.url.path for r in requests] == ["/api/v1/auth/me"]
    finally:
        client.close()


def test_both_mapping_sources_or_no_mapping_are_rejected():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    common = dict(
        base_url="https://loanhub.example.test",
        public_key=key.public_key(),
    )
    for kwargs in (
        {},
        {"resolve_borrower_mapping": lambda _: (TENANT, BORROWER),
         "resolve_remote_borrower_context": lambda *args: (TENANT, BORROWER)},
    ):
        with pytest.raises(ValueError):
            LoanHubIdentityVerifier(**common, **kwargs)


def test_invalid_origins_rejected():
    for origin in (
        "http://loanhub.example.test", "https://user:pass@loanhub.example.test",
        "https://loanhub.example.test/admin",
        "https://loanhub.example.test?token=leak",
    ):
        with pytest.raises(ValueError):
            LoanHubRemoteBorrowerContext(base_url=origin)
