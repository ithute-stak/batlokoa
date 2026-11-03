"""Controlled JWKS snapshot rollover, no real provider access."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.app.approved_jwks import ApprovedJwksSnapshot
from backend.app.auth_verification import CentralAuthVerifier

ISSUER = "https://auth.example.test"
KEY_OLD = rsa.generate_private_key(public_exponent=65537, key_size=2048)
KEY_NEW = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwk(private, kid):
    pub = private.public_key().public_numbers()
    def b64(i):
        import base64
        return base64.urlsafe_b64encode(i.to_bytes((i.bit_length()+7)//8, "big")).rstrip(b"=").decode()
    return dict(kty="RSA", kid=kid, alg="RS256", use="sig", n=b64(pub.n), e=b64(pub.e))


def signed(private, kid):
    now = datetime.now(timezone.utc)
    return jwt.encode({
        "iss": ISSUER, "aud": "batlokoa", "sub": str(uuid4()),
        "sid": str(uuid4()), "token_use": "access", "iat": now,
        "nbf": now, "exp": now + timedelta(minutes=3),
    }, private, algorithm="RS256", headers={"kid": kid})


def verified(snapshot, token):
    return CentralAuthVerifier(ISSUER, "batlokoa", snapshot).verify(token)


def test_approved_old_and_new_kids_can_overlap_during_rotation():
    snapshot = ApprovedJwksSnapshot({"keys": [
        jwk(KEY_OLD, "key-old"), jwk(KEY_NEW, "key-new")
    ]})
    assert verified(snapshot, signed(KEY_OLD, "key-old")).token_use == "access"
    assert verified(snapshot, signed(KEY_NEW, "key-new")).token_use == "access"
    after = ApprovedJwksSnapshot({"keys": [jwk(KEY_NEW, "key-new")]})
    assert verified(after, signed(KEY_NEW, "key-new")).token_use == "access"
    with pytest.raises(jwt.InvalidTokenError):
        verified(after, signed(KEY_OLD, "key-old"))


def test_unknown_kid_and_wrong_key_fail_closed():
    approved = ApprovedJwksSnapshot({"keys": [jwk(KEY_OLD, "approved")]})
    with pytest.raises(jwt.InvalidTokenError):
        verified(approved, signed(KEY_NEW, "not-approved"))
    with pytest.raises(jwt.InvalidTokenError):
        verified(approved, signed(KEY_NEW, "approved"))


def test_duplicate_missing_and_non_rsa_keys_rejected():
    old = jwk(KEY_OLD, "old")
    for rows in (
        [old, old],
        [dict(old, alg="HS256")],
        [dict(old, kty="oct")],
        [dict(old, use="enc")],
        [dict(old, kid="")],
        [],
    ):
        with pytest.raises(ValueError):
            ApprovedJwksSnapshot({"keys": rows})
