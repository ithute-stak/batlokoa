"""Opt-in read-only LoanHub registration review via POST body, not URL query.

A 'no match' result is NOT proof of a new borrower and cannot authorize
registration. Identity numbers are never echoed into API responses.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from .staff_authorization import (
    StaffAccessDenied, StaffPermission, VerifiedStaffIdentity,
    require_staff_permission,
)


class RegistrationIdentityReviewUnavailable(Exception):
    pass


@dataclass(frozen=True)
class RegistrationIdentityReview:
    decision: str
    identity_match_found: bool
    legacy_capture_found: bool
    requires_human_review: bool = True
    can_commit: bool = False


class LoanHubRegistrationReview:
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

    def review(
        self, *, staff: VerifiedStaffIdentity,
        access_token: str, branch_id: UUID, national_id: str,
    ) -> RegistrationIdentityReview:
        require_staff_permission(
            staff, expected_company_id=staff.company_id,
            branch_id=branch_id, permission=StaffPermission.REGISTER_CLIENT,
        )
        if (
            not isinstance(national_id, str)
            or not 4 <= len(national_id.strip()) <= 100
        ):
            raise ValueError("National ID is required for protected review")
        if (
            not isinstance(access_token, str) or
            not 1 <= len(access_token) <= 8192 or
            any(char.isspace() for char in access_token)
        ):
            raise StaffAccessDenied("Verified employee credential required")

        def call(client: httpx.Client):
            return client.post(
                self._origin + "/api/v1/company-clients/registration-review",
                json={
                    "national_id": national_id.strip(),
                    "branch_id": str(branch_id),
                },
                headers={
                    "Authorization": "Bearer " + access_token,
                    "X-Company-ID": str(staff.company_id),
                    "X-Active-Role": staff.role.lower(),
                    "Accept": "application/json",
                    "Cache-Control": "no-store",
                },
                timeout=5, follow_redirects=False,
            )

        try:
            if self._client is None:
                with httpx.Client(trust_env=False, follow_redirects=False) as client:
                    response = call(client)
            else:
                response = call(self._client)
            if (
                response.status_code != 200 or
                len(response.content) > 8192 or
                "application/json" not in response.headers.get(
                    "content-type", ""
                ).lower()
            ):
                raise RegistrationIdentityReviewUnavailable("Review unavailable")
            data = response.json()
            if (
                not isinstance(data, dict)
                or data.get("can_commit") is not False
                or type(data.get("requires_human_review")) is not bool
                or type(data.get("identity_match_found")) is not bool
                or type(data.get("legacy_capture_found")) is not bool
                or data.get("decision") not in {
                    "manual_review_required",
                    "new_identity_candidate",
                }
            ):
                raise RegistrationIdentityReviewUnavailable(
                    "Untrusted registration review result"
                )
            # Ignore the upstream human-review hint for clearance purposes:
            # the Batlokoa gateway always requires an independent review.
            return RegistrationIdentityReview(
                decision=data["decision"],
                identity_match_found=data["identity_match_found"],
                legacy_capture_found=data["legacy_capture_found"],
            )
        except (httpx.HTTPError, ValueError, TypeError, KeyError,
                UnicodeError) as exc:
            raise RegistrationIdentityReviewUnavailable(
                "Registration review could not be verified"
            ) from exc
