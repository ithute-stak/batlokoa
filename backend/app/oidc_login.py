"""Opt-in Batlokoa Authorization Code + PKCE browser login foundation.

No live IdP, client registration or storage backend is configured by default.
The service requires a single-use, server-side transaction store and a fixed,
trusted authorization/token endpoint. Never accept provider URLs from a user,
and never return exchanged tokens to a browser or Flutter application.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode, urlsplit
from uuid import UUID

from .auth_verification import CentralAccessClaims, CentralAuthVerifier
from .sessions import SessionGrant


class LoginDenied(Exception):
    """Invalid or already consumed authentication transaction."""


class LoginUnavailable(Exception):
    """Authentication integration is not safely configured or available."""


def _https_url(url: str) -> bool:
    parsed = urlsplit(url)
    return (parsed.scheme == "https" and bool(parsed.hostname) and
            not parsed.username and not parsed.password and
            not parsed.fragment and not parsed.query)


@dataclass(frozen=True)
class PendingLogin:
    state: str
    nonce: str
    code_verifier: str


class LoginTransactionStore(Protocol):
    async def save(self, transaction: PendingLogin, *, expires_seconds: int) -> None: ...
    async def consume(self, *, state: str) -> PendingLogin | None: ...


@dataclass(frozen=True)
class ExchangedTokens:
    access_token: str
    id_token: str


class AuthCodeExchanger(Protocol):
    async def exchange(self, *, code: str, code_verifier: str,
                       redirect_uri: str) -> ExchangedTokens:
        """Backchannel code exchange; return tokens only to server-side code."""
        ...


class IdTokenVerifier(Protocol):
    def verify(self, id_token: str, *, expected_nonce: str,
               expected_subject: str) -> None:
        """Validate signed OIDC ID token: issuer, aud, exp, iat, nonce, sub.

        An unimplemented or permissive verifier MUST NOT be injected.
        """
        ...


class SessionIssuer(Protocol):
    async def issue(self, *, claims: CentralAccessClaims,
                    tenant_id: UUID, ttl_seconds: int = 900) -> SessionGrant: ...


@dataclass(frozen=True)
class OidcLoginService:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    client_id: str
    redirect_uri: str
    tenant_id: UUID
    verifier: CentralAuthVerifier
    transactions: LoginTransactionStore
    exchanger: AuthCodeExchanger
    id_token_verifier: IdTokenVerifier
    sessions: SessionIssuer

    def __post_init__(self) -> None:
        issuer = self.issuer.rstrip("/")
        if (not _https_url(issuer) or not _https_url(self.authorization_endpoint)
                or not _https_url(self.token_endpoint) or
                not _https_url(self.redirect_uri) or
                urlsplit(self.authorization_endpoint).netloc != urlsplit(issuer).netloc or
                urlsplit(self.token_endpoint).netloc != urlsplit(issuer).netloc or
                not self.client_id or len(self.client_id) > 200 or
                self.verifier.issuer.rstrip("/") != issuer or
                self.verifier.audience != self.client_id):
            raise ValueError("OIDC endpoints, client ID or verifier are not trusted")
        if not self.redirect_uri.endswith("/api/v1/auth/callback"):
            raise ValueError("Callback URI must be the pre-registered BFF endpoint")

    async def begin(self) -> tuple[str, str]:
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        await self.transactions.save(
            PendingLogin(state=state, nonce=nonce, code_verifier=verifier),
            expires_seconds=300,
        )
        url = self.authorization_endpoint + "?" + urlencode({
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "openid",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        })
        return url, state

    async def finish(self, *, state: str, cookie_state: str, code: str) -> SessionGrant:
        if (not state or not cookie_state or len(state) > 256 or
                len(cookie_state) > 256 or
                not hmac.compare_digest(state, cookie_state) or
                not code or len(code) > 4096):
            raise LoginDenied("Invalid login callback")
        # Must consume atomically before the token request; replay must not
        # cause a second exchange or a second session issuance.
        pending = await self.transactions.consume(state=state)
        if pending is None or not hmac.compare_digest(pending.state, state):
            raise LoginDenied("Expired or already used login transaction")
        try:
            tokens = await self.exchanger.exchange(
                code=code, code_verifier=pending.code_verifier,
                redirect_uri=self.redirect_uri,
            )
            claims = self.verifier.verify(tokens.access_token)
            self.id_token_verifier.verify(
                tokens.id_token, expected_nonce=pending.nonce,
                expected_subject=claims.sub,
            )
        except Exception as exc:
            raise LoginUnavailable("Authentication exchange failed") from exc
        return await self.sessions.issue(claims=claims, tenant_id=self.tenant_id)
