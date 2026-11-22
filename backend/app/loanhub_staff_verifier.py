"""Read-only verification of LoanHub staff membership from /api/v1/auth/me.

Uses backend-held LoanHub access credentials only. Never accepts a claimed
tenant, role or branch from the app. This is an internal service, not a login
route or token storage solution. LoanHub must reauthorize every future write.
"""
from __future__ import annotations

from urllib.parse import urlsplit
from uuid import UUID

import httpx
import jwt

from .staff_authorization import VerifiedStaffIdentity


class StaffVerificationUnavailable(Exception):
    pass


class LoanHubStaffVerifier:
    def __init__(self, *, origin: str, public_key: object,
                 batlokoa_company_id: UUID, client: httpx.Client | None = None,
                 allow_unverified_company_owner: bool = False):
        parts = urlsplit(origin)
        if (parts.scheme != "https" or not parts.hostname or parts.username or
                parts.password or parts.path not in ("", "/") or parts.query or
                parts.fragment or parts.port == 0):
            raise ValueError("A pinned HTTPS LoanHub origin is required")
        if public_key is None or not isinstance(batlokoa_company_id, UUID):
            raise ValueError("Trusted key and Batlokoa company UUID are required")
        self._origin = origin.rstrip("/")
        self._public_key = public_key
        self._company_id = batlokoa_company_id
        if not isinstance(allow_unverified_company_owner, bool):
            raise ValueError("Owner pilot exception must be explicitly boolean")
        self._allow_unverified_company_owner = allow_unverified_company_owner
        self._client = client

    def verify(self, token: str) -> VerifiedStaffIdentity:
        """Resolve active Batlokoa membership. Raise on all uncertain cases."""
        try:
            if (not isinstance(token, str) or not 1 <= len(token) <= 8192
                    or any(c.isspace() for c in token)):
                raise StaffVerificationUnavailable()
            payload = jwt.decode(
                token, self._public_key, algorithms=["RS256"],
                options={"require": ["exp", "user_id", "token_type"]},
                leeway=0,
            )
            if (payload.get("token_type") != "access"
                    or not isinstance(payload.get("session_jti"), str)
                    or not payload["session_jti"]
                    or "impersonated_by" in payload):
                raise StaffVerificationUnavailable()
            user_id = UUID(str(payload["user_id"]))

            def call(client: httpx.Client):
                return client.get(
                    self._origin + "/api/v1/auth/me",
                    headers={"Authorization": "Bearer " + token,
                             "Accept": "application/json",
                             "Cache-Control": "no-store"},
                    timeout=5, follow_redirects=False,
                )
            if self._client is None:
                with httpx.Client(trust_env=False, follow_redirects=False) as client:
                    response = call(client)
            else:
                response = call(self._client)

            if (response.status_code != 200 or len(response.content) > 16384
                    or "application/json" not in
                    response.headers.get("content-type", "").lower()):
                raise StaffVerificationUnavailable()
            me = response.json()
            if (not isinstance(me, dict) or UUID(str(me.get("id"))) != user_id
                    or me.get("is_active") is not True
                    or me.get("must_change_password") is not False
                    or str(me.get("role", "")).lower() == "borrower"):
                raise StaffVerificationUnavailable()
            memberships = me.get("memberships")
            if not isinstance(memberships, list):
                raise StaffVerificationUnavailable()
            relevant = [m for m in memberships if isinstance(m, dict) and
                        str(m.get("company_id")) == str(self._company_id) and
                        m.get("is_active") is True]
            if len(relevant) != 1:
                raise StaffVerificationUnavailable()
            m = relevant[0]
            role = str(m.get("role", "")).upper()
            if role not in {
                "COMPANY_OWNER", "COMPANY_ADMIN", "BRANCH_MANAGER",
                "LOAN_OFFICER", "CREDIT_ANALYST",
            }:
                raise StaffVerificationUnavailable()
            # LoanHub's own login permits an active, unverified user.
            # Exception is strictly limited to company owners in an explicitly
            # approved read-only pilot, with a verified signed LoanHub token
            # and precisely one active membership in Batlokoa. No user flag
            # or LoanHub permission is ever changed by this adapter.
            if me.get("is_verified") is not True:
                if not (
                    self._allow_unverified_company_owner
                    and me.get("is_verified") is False
                    and role == "COMPANY_OWNER"
                ):
                    raise StaffVerificationUnavailable()
            branch_raw = m.get("branch_id")
            branch = UUID(str(branch_raw)) if branch_raw is not None else None
            if branch is None and role not in {"COMPANY_OWNER", "COMPANY_ADMIN"}:
                raise StaffVerificationUnavailable()
            return VerifiedStaffIdentity(
                user_id=user_id,
                company_id=self._company_id,
                role=role,
                active=True,
                branch_ids=frozenset({branch}) if branch else frozenset(),
                company_wide_scope=role in {"COMPANY_OWNER", "COMPANY_ADMIN"},
            )
        except (jwt.PyJWTError, httpx.HTTPError, ValueError, TypeError, KeyError,
                OverflowError, UnicodeError) as exc:
            raise StaffVerificationUnavailable("LoanHub staff identity cannot be verified") from exc
