"""LoanHub-owned read-only proof of borrower/company association.

Calls the verified LoanHub endpoint using only the borrower JWT. This avoids
introducing Batlokoa credentials with SELECT permissions on LoanHub's DB.
Not bootstrapped in the public demo; all live financial routes remain off.
"""
from __future__ import annotations

from typing import Callable
from urllib.parse import urlsplit
from uuid import UUID

import httpx


class LoanHubRemoteBorrowerContext:
    """HTTP adapter for GET /api/v1/auth/borrower-context?company_id=<uuid>."""

    def __init__(self, *, base_url: str, client: httpx.Client | None = None) -> None:
        parsed = urlsplit(base_url)
        if (parsed.scheme != "https" or not parsed.hostname or
                parsed.username or parsed.password or
                parsed.query or parsed.fragment or
                parsed.path not in ("", "/")):
            raise ValueError("LoanHub borrower-context origin must be HTTPS")
        self._origin = base_url.rstrip("/")
        self._client = client

    def __call__(
        self, token: str, user_id: str, tenant_id: str,
    ) -> tuple[str, str] | None:
        try:
            user = str(UUID(user_id))
            tenant = str(UUID(tenant_id))
            if (not isinstance(token, str) or not token or
                    len(token) > 8192 or any(ch.isspace() for ch in token)):
                return None

            def call(client: httpx.Client) -> httpx.Response:
                return client.get(
                    f"{self._origin}/api/v1/auth/borrower-context",
                    params={"company_id": tenant},
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                        "Cache-Control": "no-store",
                    },
                    timeout=5,
                    follow_redirects=False,
                )

            if self._client is None:
                with httpx.Client(trust_env=False, follow_redirects=False) as client:
                    response = call(client)
            else:
                response = call(self._client)

            if (response.status_code != 200 or len(response.content) > 4096 or
                    "application/json" not in response.headers.get(
                        "content-type", "").lower()):
                return None
            data = response.json()
            if (not isinstance(data, dict) or
                    str(UUID(str(data.get("user_id")))) != user or
                    str(UUID(str(data.get("company_id")))) != tenant or
                    data.get("role") != "borrower" or
                    data.get("session_active") is not True or
                    data.get("account_active") is not True):
                return None
            borrower = str(UUID(str(data.get("borrower_id"))))
            return (tenant, borrower)
        except Exception:
            # Never return a partial identity or leak token/DB/HTTP exception text.
            return None
