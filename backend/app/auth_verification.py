"""Strict !thute Auth access token verifier for Batlokoa (not enabled in HTTP).

Modelled against the real LoanHub services/ithute_auth_service.py contract:
RS256, exact issuer+audience, sub/sid UUID, token_use='access', nbf/iat/exp.
Key selection is obtained from an approved JWKS supplier, not token claims.
A production bootstrap must pin the trusted JWKS URL and configure rotations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

import jwt
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError

from .identity import VerifiedClaims


class SigningKeySource(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> object: ...


class CentralAuthUnavailable(Exception):
    """Signing key authority is not available; fail closed."""


@dataclass(frozen=True)
class CentralAuthVerifier:
    issuer: str
    audience: str
    keys: SigningKeySource

    def __post_init__(self) -> None:
        parsed = urlsplit(self.issuer)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ("", "/") or not self.audience.strip()):
            raise ValueError("Central Auth issuer must be a trusted HTTPS origin")

    def verify(self, token: str) -> VerifiedClaims:
        if not isinstance(token, str) or not 32 <= len(token) <= 8192:
            raise jwt.InvalidTokenError("Invalid access token")
        try:
            selected = self.keys.get_signing_key_from_jwt(token)
        except PyJWKClientConnectionError as exc:
            raise CentralAuthUnavailable("Central Auth key source unavailable") from exc
        except PyJWKClientError as exc:
            raise jwt.InvalidTokenError("Invalid signing key") from exc
        key = getattr(selected, "key", None)
        if key is None:
            raise jwt.InvalidTokenError("No trusted signing key")
        claims = jwt.decode(
            token, key, algorithms=["RS256"],
            issuer=self.issuer.rstrip("/"), audience=self.audience,
            options={"require": [
                "iss", "aud", "sub", "sid", "iat", "nbf", "exp", "token_use"
            ]},
            leeway=0,
        )
        if claims.get("token_use") != "access":
            raise jwt.InvalidTokenError("Wrong token type")
        try:
            UUID(str(claims["sub"]))
            UUID(str(claims["sid"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise jwt.InvalidTokenError("Invalid immutable subject or session ID") from exc
        return VerifiedClaims.model_validate(claims)
