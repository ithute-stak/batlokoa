from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.app.oidc_id_token import OidcIdTokenVerifier

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ISSUER = "https://auth.example.test"
SUB = str(uuid4())


class Source:
    def get_signing_key_from_jwt(self, value):
        return type("KeyRef", (), {"key": KEY.public_key()})()


def make(**kwargs):
    now = datetime.now(timezone.utc)
    payload = dict(iss=ISSUER, aud="batlokoa", sub=SUB, nonce="known-nonce",
                   iat=now, exp=now + timedelta(minutes=2))
    payload.update(kwargs)
    return jwt.encode(payload, KEY, algorithm="RS256")


def check(token, nonce="known-nonce", subject=SUB):
    OidcIdTokenVerifier(ISSUER, "batlokoa", Source()).verify(
        token, expected_nonce=nonce, expected_subject=subject)


def test_valid_signed_id_token():
    check(make())


@pytest.mark.parametrize("invalid", [
    {"aud": "loanhub"},
    {"iss": "https://other.example.test"},
    {"sub": str(uuid4())},
    {"nonce": "wrong"},
    {"azp": "unrelated"},
    {"exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
])
def test_bad_id_token_is_rejected(invalid):
    with pytest.raises(jwt.InvalidTokenError):
        check(make(**invalid))


def test_nonce_and_subject_must_match():
    with pytest.raises(jwt.InvalidTokenError):
        check(make(), nonce="wrong")
    with pytest.raises(jwt.InvalidTokenError):
        check(make(), subject=str(uuid4()))
