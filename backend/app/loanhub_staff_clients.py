"""Phase 59: read-only, least-data LoanHub staff client directory.

Internal adapter only. Caller must first resolve a real LoanHub staff session
through LoanHubStaffVerifier. LoanHub authorizes the original employee's token
again, including branch and tenant. No public route is registered here.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from .staff_authorization import (
    StaffAccessDenied,
    StaffPermission,
    VerifiedStaffIdentity,
    require_staff_permission,
)


class StaffDirectoryUnavailable(Exception):
    pass


@dataclass(frozen=True)
class StaffClientSummary:
    account_id: UUID
    account_reference: str
    company_id: UUID
    branch_id: UUID | None
    full_name: str
    status: str


class LoanHubStaffClientDirectory:
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

    def search(
        self,
        *,
        verified_staff: VerifiedStaffIdentity,
        staff_access_token: str,
        search: str = "",
        branch_id: UUID | None = None,
        limit: int = 30,
    ) -> list[StaffClientSummary]:
        """Read a restricted list, rejecting mismatched records wholesale.

        A company's owner/admin can request cross-branch reads; other staff
        members must have exactly one verified branch assignment. LoanHub
        applies the definitive company and branch restrictions.
        """
        if not isinstance(verified_staff, VerifiedStaffIdentity):
            raise StaffAccessDenied("Verified staff required")
        if not isinstance(staff_access_token, str) or not (
            1 <= len(staff_access_token) <= 8192
        ) or any(ch.isspace() for ch in staff_access_token):
            raise StaffAccessDenied("Trusted staff credential required")
        if not isinstance(search, str) or len(search) > 120:
            raise ValueError("Invalid search query")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("Invalid page size")
        if branch_id is not None and not isinstance(branch_id, UUID):
            raise ValueError("Invalid branch")
        if verified_staff.company_wide_scope:
            if verified_staff.role not in {"COMPANY_OWNER", "COMPANY_ADMIN"}:
                raise StaffAccessDenied("Management scope required")
            # Require a concrete, validated branch for any explicit branch
            # filter; no browser-provided role or company is trusted.
            if branch_id is None:
                if not verified_staff.active:
                    raise StaffAccessDenied("Inactive account")
            else:
                require_staff_permission(
                    verified_staff,
                    expected_company_id=verified_staff.company_id,
                    branch_id=branch_id,
                    permission=StaffPermission.VIEW_CLIENTS,
                )
        else:
            if len(verified_staff.branch_ids) != 1:
                raise StaffAccessDenied("A single verified branch is required")
            only_branch = next(iter(verified_staff.branch_ids))
            if branch_id is not None and branch_id != only_branch:
                raise StaffAccessDenied("Different branch is not authorized")
            branch_id = only_branch
            require_staff_permission(
                verified_staff,
                expected_company_id=verified_staff.company_id,
                branch_id=branch_id,
                permission=StaffPermission.VIEW_CLIENTS,
            )
        try:
            def call(client: httpx.Client) -> httpx.Response:
                return client.get(
                    self._origin + "/api/v1/company-clients",
                    params={
                        "search": search.strip(), "limit": limit,
                        **({"branch_id": str(branch_id)} if branch_id else {}),
                    },
                    headers={
                        "Authorization": "Bearer " + staff_access_token,
                        "X-Company-ID": str(verified_staff.company_id),
                        "X-Active-Role": verified_staff.role.lower(),
                        "Accept": "application/json",
                        "Cache-Control": "no-store",
                    },
                    follow_redirects=False, timeout=5,
                )
            if self._client is None:
                with httpx.Client(trust_env=False, follow_redirects=False) as client:
                    response = call(client)
            else:
                response = call(self._client)
            if (
                response.status_code != 200 or len(response.content) > 262144
                or "application/json" not in
                response.headers.get("content-type", "").lower()
            ):
                raise StaffDirectoryUnavailable("LoanHub directory unavailable")
            records = response.json()
            if not isinstance(records, list) or len(records) > limit:
                raise StaffDirectoryUnavailable("Unexpected directory response")
            result = []
            seen = set()
            for record in records:
                if not isinstance(record, dict):
                    raise StaffDirectoryUnavailable("Invalid client")
                account = UUID(str(record["id"]))
                company = UUID(str(record["company_id"]))
                raw_branch = record.get("branch_id")
                record_branch = UUID(str(raw_branch)) if raw_branch else None
                if (
                    account in seen or company != verified_staff.company_id
                    or (branch_id is not None and record_branch != branch_id)
                    or (not verified_staff.company_wide_scope and
                        record_branch not in verified_staff.branch_ids)
                ):
                    raise StaffDirectoryUnavailable("Directory scope mismatch")
                name = record["full_name"]
                reference = record["account_reference"]
                status = record["status"]
                if not all(isinstance(v, str) and 0 < len(v) <= 200
                           for v in (name, reference, status)):
                    raise StaffDirectoryUnavailable("Malformed client fields")
                seen.add(account)
                result.append(StaffClientSummary(
                    account_id=account, account_reference=reference,
                    company_id=company, branch_id=record_branch,
                    full_name=name, status=status,
                ))
            return result
        except (httpx.HTTPError, ValueError, KeyError, TypeError,
                UnicodeError) as error:
            raise StaffDirectoryUnavailable("LoanHub directory verification failed") from error
