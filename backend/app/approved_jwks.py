"""Offline, operator-approved RS256 JWKS snapshot for controlled key rotation.

Never fetch an untrusted JWT header's jwku/jku/x5u and never treat its kid
as a URL or file path. A new validated snapshot can be installed by an
independently authenticated deployment process; missing kid fails closed.
"""
from __future__ import annotations

from dataclasses import dataclass

import jwt
from jwt.exceptions import PyJWKClientError


@dataclass(frozen=True)
class SelectedSigningKey:
    key: object


class ApprovedJwksSnapshot:
    def __init__(self, document: object) -> None:
        if not isinstance(document, dict) or not isinstance(document.get("keys"), list):
            raise ValueError("Invalid operator-approved JWKS")
        keys = document["keys"]
        if not 1 <= len(keys) <= 16:
            raise ValueError("Invalid number of signing keys")
        approved = {}
        for row in keys:
            if not isinstance(row, dict):
                raise ValueError("Invalid signing key")
            kid = row.get("kid")
            if (not isinstance(kid, str) or not 1 <= len(kid) <= 128
                    or not kid.isascii() or kid in approved
                    or row.get("kty") != "RSA" or row.get("alg") != "RS256"
                    or row.get("use", "sig") != "sig"
                    or "verify" not in row.get("key_ops", ["verify"])):
                raise ValueError("Unsupported, ambiguous or duplicate JWKS key")
            try:
                loaded = jwt.PyJWK.from_dict(row, algorithm="RS256")
            except (ValueError, TypeError, jwt.PyJWTError) as exc:
                raise ValueError("Invalid RS256 public key") from exc
            if loaded.key.key_size < 2048:
                raise ValueError("Insufficient RSA signing key size")
            approved[kid] = loaded.key
        self._approved = approved

    @property
    def kids(self) -> tuple[str, ...]:
        return tuple(self._approved)

    def get_signing_key_from_jwt(self, token: str) -> SelectedSigningKey:
        try:
            header = jwt.get_unverified_header(token)
        except (jwt.PyJWTError, TypeError, ValueError) as exc:
            raise PyJWKClientError("Malformed token header") from exc
        if header.get("alg") != "RS256":
            raise PyJWKClientError("Unexpected signing algorithm")
        kid = header.get("kid")
        if not isinstance(kid, str) or kid not in self._approved:
            raise PyJWKClientError("Unknown signing key")
        return SelectedSigningKey(self._approved[kid])
