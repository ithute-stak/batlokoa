"""Strict OIDC discovery metadata validation for a pinned central Auth issuer.

This module does not enable Batlokoa customer login. Production deployment
requires operator-reviewed discovery metadata, a registered Batlokoa client,
a stable pinned JWKS URL, and separately provisioned backchannel credentials.

Never use a discovery URL, JWKS URL or endpoint supplied by a browser or
contained in an unverified JWT.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx


class DiscoveryUnavailable(Exception):
    """Provider metadata cannot be safely fetched or validated."""


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or
            parsed.username is not None or parsed.password is not None or
            parsed.query or parsed.fragment or
            parsed.port is not None or not parsed.netloc):
        raise ValueError("Invalid HTTPS OIDC endpoint")
    return f"https://{parsed.hostname}"


def _trusted_endpoint(url: object, issuer_origin: str) -> str:
    if not isinstance(url, str) or len(url) > 1024:
        raise DiscoveryUnavailable("Invalid OIDC endpoint")
    parsed = urlsplit(url)
    try:
        origin = _origin(url)
    except ValueError as exc:
        raise DiscoveryUnavailable("Untrusted OIDC endpoint") from exc
    if origin != issuer_origin or not parsed.path.startswith("/") or (
        "//" in parsed.path or "/../" in parsed.path or
        parsed.path.endswith("/..") or "/./" in parsed.path
    ):
        raise DiscoveryUnavailable("OIDC endpoint outside trusted issuer origin")
    return url


@dataclass(frozen=True, slots=True)
class VerifiedOidcMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    token_endpoint_auth_methods_supported: tuple[str, ...]


def parse_discovery(
    payload: object, *, expected_issuer: str, public_client: bool = True
) -> VerifiedOidcMetadata:
    """Refuse any issuer, token method, key URL or PKCE policy drift."""
    if not isinstance(payload, dict):
        raise DiscoveryUnavailable("Invalid OIDC discovery document")
    try:
        expected_origin = _origin(expected_issuer)
    except ValueError as exc:
        raise DiscoveryUnavailable("Invalid expected issuer") from exc
    if expected_issuer != expected_origin:
        raise DiscoveryUnavailable("Expected issuer must be an exact HTTPS origin")
    if payload.get("issuer") != expected_issuer:
        raise DiscoveryUnavailable("Unexpected OIDC issuer")
    algs = payload.get("id_token_signing_alg_values_supported")
    if not isinstance(algs, list) or "RS256" not in algs:
        raise DiscoveryUnavailable("OIDC RS256 is not advertised")
    response_types = payload.get("response_types_supported")
    if not isinstance(response_types, list) or "code" not in response_types:
        raise DiscoveryUnavailable("Authorization code grant not supported")
    grant_types = payload.get("grant_types_supported")
    if grant_types is not None and (
        not isinstance(grant_types, list) or "authorization_code" not in grant_types
    ):
        raise DiscoveryUnavailable("Authorization code grant not supported")
    methods = payload.get("code_challenge_methods_supported")
    if not isinstance(methods, list) or "S256" not in methods:
        raise DiscoveryUnavailable("PKCE S256 is not advertised")
    auth_methods = payload.get("token_endpoint_auth_methods_supported")
    if auth_methods is None:
        raise DiscoveryUnavailable("Token authentication method not explicitly advertised")
    if not isinstance(auth_methods, list) or any(
        not isinstance(method, str) for method in auth_methods
    ):
        raise DiscoveryUnavailable("Invalid token authentication methods")
    # The existing Batlokoa backchannel exchanger is a public PKCE client and
    # sends client_id in the form. It does NOT authenticate with a client secret.
    # Refuse provider metadata that requires a confidential client until the
    # client auth contract has been implemented and separately tested.
    if public_client and "none" not in auth_methods:
        raise DiscoveryUnavailable("Provider requires unsupported client authentication")
    return VerifiedOidcMetadata(
        issuer=expected_issuer,
        authorization_endpoint=_trusted_endpoint(
            payload.get("authorization_endpoint"), expected_origin),
        token_endpoint=_trusted_endpoint(payload.get("token_endpoint"), expected_origin),
        jwks_uri=_trusted_endpoint(payload.get("jwks_uri"), expected_origin),
        token_endpoint_auth_methods_supported=tuple(auth_methods),
    )


@dataclass(frozen=True)
class OidcDiscoveryClient:
    expected_issuer: str
    public_client: bool = True
    transport: httpx.AsyncBaseTransport | None = None

    async def fetch(self) -> VerifiedOidcMetadata:
        try:
            issuer_origin = _origin(self.expected_issuer)
            if self.expected_issuer != issuer_origin:
                raise ValueError("OIDC issuer must be an exact HTTPS origin")
        except ValueError as exc:
            raise DiscoveryUnavailable("Untrusted OIDC discovery issuer") from exc
        try:
            async with httpx.AsyncClient(
                trust_env=False, follow_redirects=False,
                timeout=5.0, transport=self.transport,
            ) as client:
                response = await client.get(
                    self.expected_issuer + "/.well-known/openid-configuration",
                    headers={"Accept": "application/json", "Cache-Control": "no-store"},
                    follow_redirects=False,
                )
        except httpx.HTTPError as exc:
            raise DiscoveryUnavailable("OIDC provider metadata unavailable") from exc
        if (response.status_code != 200 or len(response.content) > 65_536 or
                "application/json" not in response.headers.get("content-type", "")):
            raise DiscoveryUnavailable("OIDC discovery request unsuccessful")
        try:
            payload = response.json()
        except ValueError as exc:
            raise DiscoveryUnavailable("OIDC provider returned invalid JSON") from exc
        return parse_discovery(
            payload, expected_issuer=self.expected_issuer,
            public_client=self.public_client,
        )
