"""Strict OIDC ID-token verifier, using only a bootstrap-pinned JWKS source."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID
from urllib.parse import urlsplit

import jwt
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError

from .auth_verification import CentralAuthUnavailable, SigningKeySource


@dataclass(frozen=True)
class OidcIdTokenVerifier:
    issuer: str
    client_id: str
    keys: SigningKeySource

    def __post_init__(self) -> None:
        issuer = urlsplit(self.issuer)
        if issuer.scheme != "https" or not issuer.hostname or not self.client_id:
            raise ValueError("Untrusted OIDC ID-token configuration")

    def verify(self, id_token: str, *, expected_nonce: str, expected_subject: str) -> None:
        if (not isinstance(id_token, str) or not 32 <= len(id_token) <= 8192
                or not expected_nonce or len(expected_nonce) > 256):
            raise jwt.InvalidTokenError("Invalid OIDC ID token")
        try:
            key = self.keys.get_signing_key_from_jwt(id_token).key
        except PyJWKClientConnectionError as exc:
            raise CentralAuthUnavailable("OIDC verification keys unavailable") from exc
        except PyJWKClientError as exc:
            raise jwt.InvalidTokenError("OIDC key not trusted") from exc
        claims = jwt.decode(
            id_token, key, algorithms=["RS256"],
            issuer=self.issuer.rstrip("/"), audience=self.client_id,
            options={"require": ["iss", "aud", "sub", "exp", "iat", "nonce"]},
            leeway=0,
        )
        try:
            UUID(str(claims["sub"]))
        except (TypeError, ValueError) as exc:
            raise jwt.InvalidTokenError("Invalid OIDC subject") from exc
        if (claims["sub"] != expected_subject or
                claims["nonce"] != expected_nonce or
                claims.get("azp", self.client_id) != self.client_id):
            raise jwt.InvalidTokenError("OIDC subject or nonce mismatch")
