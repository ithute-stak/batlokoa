"""Source-aligned LoanHub /auth/me verifier tests; no live credentials."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.app.loanhub_identity_verifier import LoanHubIdentityVerifier

TENANT = "d921126e-e1a7-482e-ad1b-6e99b1682e19"
BORROWER = "cb6700f8-1808-46ca-bfc2-f030ad0e2d7c"
OTHER_TENANT = "9ff995dc-ad87-4a91-8a8f-18ddfc85d991"
OTHER_BORROWER = "9ff995dc-ad87-4a91-8a8f-18ddfc85d992"
USER = "72de5a5b-ad44-4eea-b871-81479fe7b045"
PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def signed(**overrides):
    payload = dict(
        user_id=USER, token_type="access", role="borrower",
        session_version=1, session_jti=str(uuid4()),
        exp=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    payload.update(overrides)
    return jwt.encode(payload, PRIVATE, algorithm="RS256")


def me(**overrides):
    data = dict(
        id=USER, role="borrower", is_active=True, is_verified=True,
        must_change_password=False,
    )
    data.update(overrides)
    return data


def setup(*, user=None, mapping=(TENANT, BORROWER), status=200, key=None):
    requests, lookups = [], []
    user = me() if user is None else user

    def handle(request):
        requests.append(request)
        return httpx.Response(status, json=user)

    client = httpx.Client(transport=httpx.MockTransport(handle))
    verifier = LoanHubIdentityVerifier(
        base_url="https://loanhub.test.example",
        public_key=PRIVATE.public_key() if key is None else key,
        resolve_borrower_mapping=lambda user_id: (
            lookups.append(user_id) or mapping),
        client=client)
    return verifier, client, requests, lookups


def test_signed_local_borrower_session_and_trusted_mapping_success():
    verify, client, requests, lookups = setup()
    token = signed()
    try:
        proof = verify(token, TENANT, BORROWER)
    finally:
        client.close()
    assert proof is not None
    assert proof.role == "borrower" and proof.session_active
    assert proof.borrower_id == BORROWER and proof.tenant_id == TENANT
    assert len(requests) == 1
    assert requests[0].url.path == "/api/v1/auth/me"
    assert requests[0].method == "GET"
    assert requests[0].headers["authorization"] == "Bearer " + token
    assert "x-company-id" not in requests[0].headers
    assert lookups == [USER]


@pytest.mark.parametrize("payload", [
    {"token_type": "refresh"},
    {"token_type": "access", "session_jti": ""},
    {"session_jti": None},
    {"impersonated_by": "admin-1"},
    {"exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
    {"user_id": "invalid-id"},
])
def test_invalid_local_jwt_never_contacts_auth_me_or_mapping(payload):
    verify, client, requests, lookups = setup()
    try:
        assert verify(signed(**payload), TENANT, BORROWER) is None
    finally:
        client.close()
    assert requests == [] and lookups == []


def test_untrusted_signature_is_rejected_before_network():
    verify, client, requests, lookups = setup()
    try:
        token = jwt.encode(
            {"user_id": USER, "token_type": "access",
             "session_jti": str(uuid4()),
             "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
            OTHER_KEY, algorithm="RS256")
        assert verify(token, TENANT, BORROWER) is None
    finally:
        client.close()
    assert requests == [] and lookups == []


@pytest.mark.parametrize("user", [
    me(role="superadmin"),
    me(role="company_admin"),
    me(role="staff"),
    me(id=str(uuid4())),
    me(is_active=False),
    me(is_verified=False),
    me(must_change_password=True),
    {"id": USER, "role": "borrower"},
])
def test_effective_remote_user_never_grants_unsafe_access(user):
    verify, client, requests, lookups = setup(user=user)
    try:
        assert verify(signed(), TENANT, BORROWER) is None
    finally:
        client.close()
    assert len(requests) == 1
    assert lookups == []


@pytest.mark.parametrize("mapping", [
    None,
    (OTHER_TENANT, BORROWER),
    (TENANT, OTHER_BORROWER),
    (USER, BORROWER),
    ("invalid-tenant", BORROWER),
    {"tenant_id": TENANT, "borrower_id": BORROWER},
])
def test_missing_or_cross_tenant_borrower_mapping_fails_closed(mapping):
    verify, client, requests, lookups = setup(mapping=mapping)
    try:
        assert verify(signed(), TENANT, BORROWER) is None
    finally:
        client.close()
    assert len(requests) == 1 and lookups == [USER]


@pytest.mark.parametrize("status", [301, 401, 403, 404, 429, 500, 503])
def test_auth_me_failures_are_not_authorization(status):
    verify, client, requests, lookups = setup(status=status)
    try:
        assert verify(signed(), TENANT, BORROWER) is None
    finally:
        client.close()
    assert len(requests) == 1 and lookups == []


def test_revoked_remote_session_after_success_cannot_reuse_old_proof():
    state = {"active": True}
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200 if state["active"] else 401, json=me())

    client = httpx.Client(transport=httpx.MockTransport(handle))
    verify = LoanHubIdentityVerifier(
        base_url="https://loanhub.test.example",
        public_key=PRIVATE.public_key(),
        resolve_borrower_mapping=lambda _: (TENANT, BORROWER), client=client)
    token = signed()
    try:
        assert verify(token, TENANT, BORROWER) is not None
        state["active"] = False
        assert verify(token, TENANT, BORROWER) is None
    finally:
        client.close()
    assert len(requests) == 2


@pytest.mark.parametrize("origin", [
    "http://loanhub.test.example",
    "https://user:password@loanhub.test.example",
    "https://loanhub.test.example/api/v1/auth/me",
    "https://loanhub.test.example/?token=1",
])
def test_identity_verifier_rejects_untrusted_base_urls(origin):
    with pytest.raises(ValueError):
        LoanHubIdentityVerifier(
            base_url=origin,
            public_key=PRIVATE.public_key(),
            resolve_borrower_mapping=lambda _: (TENANT, BORROWER))
