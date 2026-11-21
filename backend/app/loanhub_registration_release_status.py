"""Verified LoanHub registration release status, never a permission to create.

This is a read-only check of the LoanHub policy flag. No borrower PII is
accepted, and an outage or unexpected response always keeps writes disabled.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from .staff_authorization import StaffAccessDenied, VerifiedStaffIdentity


class RegistrationReleaseStatusUnavailable(Exception):
    pass


@dataclass(frozen=True)
class RegistrationReleaseStatus:
    can_submit: bool = False
    state: str = "not_released"
    requires_identity_migration_approval: bool = True
    requires_independent_release_approval: bool = True


class LoanHubRegistrationReleaseStatus:
    def __init__(self, *, origin: str, client: httpx.Client | None = None):
        parsed = urlsplit(origin)
        if (
            parsed.scheme != "https" or not parsed.hostname
            or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment
        ):
            raise ValueError("Pinned HTTPS LoanHub origin required")
        self._origin = origin.rstrip("/")
        self._client = client

    def inspect(
        self, *, staff: VerifiedStaffIdentity, access_token: str
    ) -> RegistrationReleaseStatus:
        if (
            not isinstance(staff, VerifiedStaffIdentity)
            or not staff.active
            or not access_token
            or not isinstance(access_token, str)
            or len(access_token) > 8192
            or any(c.isspace() for c in access_token)
        ):
            raise StaffAccessDenied("Verified staff required")

        def call(client: httpx.Client):
            return client.get(
                self._origin + "/api/v1/batlokoa/registration/availability",
                headers={
                    "Authorization": "Bearer " + access_token,
                    "X-Company-ID": str(staff.company_id),
                    "X-Active-Role": staff.role.lower(),
                    "Accept": "application/json",
                    "Cache-Control": "no-store",
                },
                timeout=5,
                follow_redirects=False,
            )

        try:
            if self._client is None:
                with httpx.Client(trust_env=False, follow_redirects=False) as client:
                    response = call(client)
            else:
                response = call(self._client)
            if (
                response.status_code != 200
                or len(response.content) > 8192
                or "application/json" not in
                response.headers.get("content-type", "").lower()
            ):
                raise RegistrationReleaseStatusUnavailable(
                    "LoanHub registration status unavailable"
                )
            data = response.json()
            if not isinstance(data, dict) or any(
                type(data.get(k)) is not bool for k in (
                    "new_only_registration_available",
                    "can_submit_new_only_registration",
                    "requires_identity_migration_approval",
                    "requires_independent_release_approval",
                )
            ) or not isinstance(data.get("reason_code"), str):
                raise RegistrationReleaseStatusUnavailable(
                    "Invalid LoanHub registration status contract"
                )
            # No release is authorized by this adapter. Even a future
            # LoanHub true flag requires separate independently approved
            # writer routing, schema audit, and business authorization.
            return RegistrationReleaseStatus()
        except (httpx.HTTPError, ValueError, TypeError, UnicodeError) as exc:
            raise RegistrationReleaseStatusUnavailable(
                "LoanHub release status could not be verified"
            ) from exc
