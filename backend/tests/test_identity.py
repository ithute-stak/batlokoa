from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import InvalidTokenError

from backend.app.identity import (
    CustomerContext,
    NoCustomersDirectory,
    VerifiedClaims,
    resolve_customer,
    validate_access_token,
)

ISSUER = "https://auth.example.test"
AUDIENCE = "batlokoa-gateway"

private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
public = private.public_key()


def token(**changes):
    now = datetime.now(timezone.utc)
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "immutable-user-123",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    payload.update(changes)
    return jwt.encode(payload, private, algorithm="RS256")


def test_valid_signed_token():
    claims = validate_access_token(
        token(), issuer=ISSUER, audience=AUDIENCE, public_key=public
    )
    assert claims.sub == "immutable-user-123"


@pytest.mark.parametrize(
    "changes",
    [
        {"aud": "unrelated-service"},
        {"iss": "https://other-issuer.test"},
        {"exp": datetime.now(timezone.utc) - timedelta(seconds=5)},
        {"sub": ""},
    ],
)
def test_invalid_claims_rejected(changes):
    with pytest.raises((InvalidTokenError, ValueError)):
        validate_access_token(
            token(**changes), issuer=ISSUER, audience=AUDIENCE, public_key=public
        )


def test_wrong_signing_key_rejected():
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(InvalidTokenError):
        validate_access_token(token(), issuer=ISSUER, audience=AUDIENCE,
                              public_key=other.public_key())


def test_unsigned_token_is_rejected():
    unsigned = jwt.encode({"sub": "x"}, key="", algorithm="none")
    with pytest.raises(InvalidTokenError):
        validate_access_token(unsigned, issuer=ISSUER, audience=AUDIENCE,
                              public_key=public)


class Directory:
    def __init__(self, context):
        self.context = context

    async def lookup(self, *, issuer, subject):
        assert issuer == ISSUER
        assert subject == "immutable-user-123"
        return self.context


@pytest.mark.asyncio
async def test_directory_absent_fails_closed():
    claims = VerifiedClaims(sub="immutable-user-123", iss=ISSUER,
                            aud=AUDIENCE, exp=2_000_000_000, iat=1_800_000_000)
    assert await resolve_customer(claims=claims, directory=NoCustomersDirectory(),
                                  permitted_tenant_id="batlokoa") is None


@pytest.mark.asyncio
async def test_cross_tenant_mapping_rejected():
    claims = VerifiedClaims(sub="immutable-user-123", iss=ISSUER,
                            aud=AUDIENCE, exp=2_000_000_000, iat=1_800_000_000)
    directory = Directory(CustomerContext(tenant_id="other-business",
                                          customer_id="cust-1",
                                          auth_subject="immutable-user-123"))
    assert await resolve_customer(claims=claims, directory=directory,
                                  permitted_tenant_id="batlokoa") is None


@pytest.mark.asyncio
async def test_correct_server_mapping_accepted():
    claims = VerifiedClaims(sub="immutable-user-123", iss=ISSUER,
                            aud=AUDIENCE, exp=2_000_000_000, iat=1_800_000_000)
    directory = Directory(CustomerContext(tenant_id="batlokoa",
                                          customer_id="cust-1",
                                          auth_subject="immutable-user-123"))
    result = await resolve_customer(claims=claims, directory=directory,
                                    permitted_tenant_id="batlokoa")
    assert result is not None and result.customer_id == "cust-1"


@pytest.mark.asyncio
async def test_subject_mismatch_rejected():
    claims = VerifiedClaims(sub="immutable-user-123", iss=ISSUER,
                            aud=AUDIENCE, exp=2_000_000_000, iat=1_800_000_000)
    directory = Directory(CustomerContext(tenant_id="batlokoa",
                                          customer_id="cust-1",
                                          auth_subject="different-person"))
    assert await resolve_customer(claims=claims, directory=directory,
                                  permitted_tenant_id="batlokoa") is None
