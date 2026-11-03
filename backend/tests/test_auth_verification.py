from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.exceptions import InvalidTokenError, PyJWKClientConnectionError

from backend.app.auth_verification import (
    CentralAuthUnavailable, CentralAuthVerifier,
)

ISSUER = "https://auth.ithute.co.ls"
AUDIENCE = "batlokoa"
PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class Selected:
    def __init__(self, key):
        self.key = key


class KeySource:
    def __init__(self, key=PRIVATE.public_key(), *, unavailable=False):
        self.key = key
        self.unavailable = unavailable

    def get_signing_key_from_jwt(self, token):
        if self.unavailable:
            raise PyJWKClientConnectionError("Key source not reachable")
        return Selected(self.key)


def encoded(**kwargs):
    now = datetime.now(timezone.utc)
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(uuid4()),
        "sid": str(uuid4()),
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=5),
        "token_use": "access",
    }
    payload.update(kwargs)
    return jwt.encode(payload, PRIVATE, algorithm="RS256", headers={"kid": "staging-key-1"})


def verifier(key_source=None):
    return CentralAuthVerifier(ISSUER, AUDIENCE, key_source or KeySource())


def test_real_signed_access_contract():
    claims = verifier().verify(encoded())
    assert claims.iss == ISSUER
    assert claims.token_use == "access"
    assert claims.sid


@pytest.mark.parametrize("changes", [
    {"aud": "loanhub"},
    {"iss": "https://other.example.test"},
    {"token_use": "refresh"},
    {"sid": "not-uuid"},
    {"sub": "not-uuid"},
    {"exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
    {"nbf": datetime.now(timezone.utc) + timedelta(minutes=2)},
])
def test_bad_token_claims_rejected(changes):
    with pytest.raises((InvalidTokenError, ValueError)):
        verifier().verify(encoded(**changes))


def test_wrong_signer_and_unsigned_tokens_rejected():
    with pytest.raises(InvalidTokenError):
        verifier(KeySource(OTHER.public_key())).verify(encoded())
    with pytest.raises(InvalidTokenError):
        verifier().verify(jwt.encode({"sub": str(uuid4())}, "", algorithm="none"))


def test_unavailable_key_authority_fails_closed():
    with pytest.raises(CentralAuthUnavailable):
        verifier(KeySource(unavailable=True)).verify(encoded())


def test_untrusted_issuer_rejected():
    with pytest.raises(ValueError):
        CentralAuthVerifier("http://auth.ithute.co.ls", AUDIENCE, KeySource())
