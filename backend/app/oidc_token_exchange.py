"""Strict server-to-server OAuth authorization code exchange (not activated).

The endpoint is injected from reviewed !thute Auth discovery configuration.
The browser never receives tokens and cannot supply the endpoint, redirect
URI, client ID or code verifier. Never log access or ID tokens.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from .oidc_login import ExchangedTokens, LoginUnavailable


@dataclass(frozen=True)
class BackchannelCodeExchanger:
    token_endpoint: str
    client_id: str
    expected_redirect_uri: str

    def __post_init__(self) -> None:
        parsed = urlsplit(self.token_endpoint)
        redirect = urlsplit(self.expected_redirect_uri)
        if (parsed.scheme != "https" or not parsed.hostname or
                parsed.username or parsed.password or parsed.query or parsed.fragment or
                redirect.scheme != "https" or not redirect.hostname or
                redirect.username or redirect.password or redirect.query or redirect.fragment or
                not self.client_id or len(self.client_id) > 200):
            raise ValueError("Untrusted OAuth token exchange configuration")

    async def exchange(self, *, code: str, code_verifier: str,
                       redirect_uri: str) -> ExchangedTokens:
        if (redirect_uri != self.expected_redirect_uri or
                not isinstance(code, str) or not 1 <= len(code) <= 4096 or
                not isinstance(code_verifier, str) or
                not 43 <= len(code_verifier) <= 128 or not code_verifier.isascii()):
            raise LoginUnavailable("Invalid OAuth code exchange context")
        try:
            async with httpx.AsyncClient(trust_env=False, follow_redirects=False,
                                         timeout=5.0) as client:
                response = await client.post(
                    self.token_endpoint,
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "code_verifier": code_verifier,
                        "redirect_uri": self.expected_redirect_uri,
                        "client_id": self.client_id,
                    },
                    headers={"Accept": "application/json", "Cache-Control": "no-store"},
                    follow_redirects=False,
                )
        except httpx.HTTPError as exc:
            raise LoginUnavailable("Identity provider exchange unavailable") from exc
        if (response.status_code != 200 or len(response.content) > 32_768 or
                "application/json" not in response.headers.get("content-type", "")):
            raise LoginUnavailable("Identity provider exchange unsuccessful")
        try:
            body = response.json()
        except ValueError as exc:
            raise LoginUnavailable("Invalid identity provider response") from exc
        if not isinstance(body, dict) or body.get("token_type", "").lower() != "bearer":
            raise LoginUnavailable("Invalid identity provider response")
        access, id_token = body.get("access_token"), body.get("id_token")
        if (not isinstance(access, str) or not isinstance(id_token, str)
                or not 32 <= len(access) <= 8192 or not 32 <= len(id_token) <= 8192):
            raise LoginUnavailable("Missing signed authentication tokens")
        return ExchangedTokens(access_token=access, id_token=id_token)
