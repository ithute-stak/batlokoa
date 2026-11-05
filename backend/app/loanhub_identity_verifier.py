"""Backend-only verifier for LoanHub's existing GET /api/v1/auth/me contract.

Not registered in the Batlokoa gateway; no credentials provisioned here.

LoanHub's /auth/me verifies the bearer token against its own user/session DB,
but does NOT expose borrower_profile.id or tenant-company association. An
independently trusted server-side mapping resolver is therefore mandatory.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlsplit
from uuid import UUID

import httpx
import jwt

from .loanhub_grant_broker import BorrowerAccountEvidence

# Map a verified local LoanHub user UUID to the borrower profile and company
# using a trusted backend data source, never headers, caller parameters or /me.
BorrowerMappingResolver = Callable[[str], tuple[str, str] | None]
RemoteBorrowerContextResolver = Callable[[str, str, str], tuple[str, str] | None]


class LoanHubIdentityVerifier:
    """Verify signed LoanHub credentials and the remote effective account.

    Caller must supply a pinned trusted public key and independently trusted
    borrower profile resolver. Both must be reviewed before deployment.
    """

    def __init__(
        self,
        *,
        base_url: str,
        public_key: object,
        resolve_borrower_mapping: BorrowerMappingResolver | None = None,
        resolve_remote_borrower_context: RemoteBorrowerContextResolver | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        origin = urlsplit(base_url)
        if (origin.scheme != "https" or not origin.hostname or
                origin.path not in ("", "/") or origin.query or origin.fragment or
                origin.username or origin.password):
            raise ValueError("LoanHub verification origin must be HTTPS")
        if (public_key is None or
                (callable(resolve_borrower_mapping) == callable(resolve_remote_borrower_context))):
            raise ValueError("Trusted LoanHub key and exactly one mapping source required")
        self._origin = base_url.rstrip("/")
        self._public_key = public_key
        self._resolve_mapping = resolve_borrower_mapping
        self._resolve_remote_context = resolve_remote_borrower_context
        self._client = client

    def __call__(
        self, token: str, tenant_id: str, borrower_id: str
    ) -> BorrowerAccountEvidence | None:
        """Fail closed for any invalid credential, mapping or service response."""
        try:
            tenant = str(UUID(tenant_id))
            borrower = str(UUID(borrower_id))
            if (not isinstance(token, str) or len(token) > 8192 or
                    not token or any(ch.isspace() for ch in token)):
                return None

            # LoanHub's local access tokens are RS256-signed, include user_id,
            # exp and token_type. Reject impersonation and tokens without a
            # session JTI; the latter cannot be checked against refresh-token
            # revocation in LoanHub's _current_local_user.
            payload = jwt.decode(
                token, self._public_key, algorithms=["RS256"],
                options={"require": ["exp", "user_id", "token_type"]},
                leeway=0,
            )
            if (payload.get("token_type") != "access" or
                    not isinstance(payload.get("session_jti"), str) or
                    not payload["session_jti"] or
                    "impersonated_by" in payload):
                return None
            user_id = str(UUID(str(payload["user_id"])))
            expiry = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
            if expiry <= datetime.now(timezone.utc):
                return None

            def call(client: httpx.Client) -> httpx.Response:
                return client.get(
                    f"{self._origin}/api/v1/auth/me",
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
            if (response.status_code != 200 or
                    len(response.content) > 16384 or
                    "application/json" not in response.headers.get(
                        "content-type", "").lower()):
                return None
            me = response.json()
            if (not isinstance(me, dict) or
                    str(UUID(str(me.get("id")))) != user_id or
                    me.get("role") != "borrower" or
                    me.get("is_active") is not True or
                    me.get("is_verified") is not True or
                    me.get("must_change_password") is not False):
                return None

            # /auth/me does not expose borrower_profile.id. Therefore do not
            # infer it from user.id, token claims, email, phone or query args.
            mapping = (
                self._resolve_remote_context(token, user_id, tenant)
                if self._resolve_remote_context is not None
                else self._resolve_mapping(user_id)
            )
            if (not isinstance(mapping, tuple) or len(mapping) != 2 or
                    str(UUID(str(mapping[0]))) != tenant or
                    str(UUID(str(mapping[1]))) != borrower):
                return None
            return BorrowerAccountEvidence(
                tenant_id=tenant, borrower_id=borrower, role="borrower",
                account_active=True, session_active=True,
                verified_at=datetime.now(timezone.utc),
                token_expires_at=expiry,
            )
        except (ValueError, TypeError, AttributeError, OverflowError,
                jwt.PyJWTError, httpx.HTTPError, KeyError):
            return None
        except Exception:
            # Do not expose secrets from a failed private mapping/transport.
            return None
