"""Strictly authenticated identity and tenant mapping primitives.

No consumer identity is inferred from a phone number, email, request header or
browser-supplied tenant identifier. These are building blocks; gateway finance
routes remain explicitly disabled until real auth and mapping are provisioned.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import jwt
from jwt import InvalidTokenError
from pydantic import BaseModel, ConfigDict, Field


class VerifiedClaims(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sub: str = Field(min_length=1, max_length=255)
    iss: str = Field(min_length=1)
    aud: str | list[str]
    exp: int
    iat: int


@dataclass(frozen=True)
class CustomerContext:
    tenant_id: str
    customer_id: str
    auth_subject: str


class CustomerDirectory(Protocol):
    """Authorized server-side mapping, not untrusted token claims."""

    async def lookup(self, *, issuer: str, subject: str) -> CustomerContext | None: ...


class NoCustomersDirectory:
    """Safe default: no active tenant/customer mappings."""

    async def lookup(self, *, issuer: str, subject: str) -> CustomerContext | None:
        return None


def validate_access_token(
    raw_token: str,
    *,
    issuer: str,
    audience: str,
    public_key: object,
) -> VerifiedClaims:
    """Validate RS256 signature + essential OAuth/OIDC token claims."""
    if not issuer.startswith("https://") or not audience.strip():
        raise ValueError("Issuer must be HTTPS and audience must be configured")
    if not raw_token or len(raw_token) > 8192:
        raise InvalidTokenError("Invalid access token length")
    payload = jwt.decode(
        raw_token,
        key=public_key,
        algorithms=["RS256"],
        audience=audience,
        issuer=issuer,
        options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        leeway=0,
    )
    return VerifiedClaims.model_validate(payload)


async def resolve_customer(
    *,
    claims: VerifiedClaims,
    directory: CustomerDirectory,
    permitted_tenant_id: str,
) -> CustomerContext | None:
    """Return context only when the server-side mapping matches this tenant."""
    if not permitted_tenant_id:
        return None
    context = await directory.lookup(issuer=claims.iss, subject=claims.sub)
    if context is None:
        return None
    if context.tenant_id != permitted_tenant_id or context.auth_subject != claims.sub:
        return None
    if not context.customer_id or not context.tenant_id:
        return None
    return context
