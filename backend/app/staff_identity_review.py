"""Read-only registration identity review. No client writes."""
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID
import httpx

from .staff_authorization import VerifiedStaffIdentity, StaffPermission, require_staff_permission


class IdentityReviewUnavailable(Exception):
    pass


@dataclass(frozen=True)
class IdentityReviewResult:
    company_id: UUID
    employee_id: UUID
    status: str
    legacy_count: int
    borrower_found: bool
    already_company_client: bool
    can_register: bool = False


class LoanHubIdentityReview:
    def __init__(self, *, origin: str, client: httpx.Client | None = None):
        p = urlsplit(origin)
        if p.scheme != "https" or not p.hostname or p.path not in ("", "/") or p.query or p.fragment or p.username or p.password:
            raise ValueError("Approved HTTPS origin required")
        self.origin = origin.rstrip("/")
        self.client = client

    def review(self, *, staff: VerifiedStaffIdentity, access_token: str,
               branch_id: UUID, national_id: str) -> IdentityReviewResult:
        require_staff_permission(
            staff, expected_company_id=staff.company_id,
            branch_id=branch_id, permission=StaffPermission.REGISTER_CLIENT)
        if not isinstance(national_id, str) or not 4 <= len(national_id.strip()) <= 100:
            raise ValueError("National ID required")
        if not isinstance(access_token, str) or not 1 <= len(access_token) <= 8192 or any(c.isspace() for c in access_token):
            raise IdentityReviewUnavailable("Trusted employee session required")
        def get(client):
            return client.get(
                self.origin + "/api/v1/company-clients/existing-loan-check",
                params={"national_id": national_id.strip()},
                headers={
                    "Authorization": "Bearer " + access_token,
                    "X-Company-ID": str(staff.company_id),
                    "X-Active-Role": staff.role.lower(),
                    "Accept": "application/json", "Cache-Control": "no-store"},
                timeout=5, follow_redirects=False)
        try:
            if self.client is None:
                with httpx.Client(trust_env=False, follow_redirects=False) as client:
                    response = get(client)
            else:
                response = get(self.client)
            if (response.status_code != 200 or len(response.content) > 65536
                    or "application/json" not in response.headers.get("content-type", "").lower()):
                raise IdentityReviewUnavailable("Review unavailable")
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("national_id"), str) or data["national_id"].strip().casefold() != national_id.strip().casefold():
                raise IdentityReviewUnavailable("Identity mismatch")
            count = data.get("legacy_capture_count")
            if type(count) is not int or not 0 <= count <= 1000000:
                raise IdentityReviewUnavailable("Invalid legacy result")
            flags = ("borrower_found", "already_company_client", "has_existing_loans")
            if any(type(data.get(k)) is not bool for k in flags):
                raise IdentityReviewUnavailable("Invalid review result")
            borrower, linked, loans = (data[k] for k in flags)
            if linked and not borrower:
                raise IdentityReviewUnavailable("Conflicting review evidence")
            status = ("existing_company_client" if linked else
                      "legacy_review_required" if count else
                      "existing_borrower_review_required" if borrower or loans else
                      "no_existing_record_reported")
            return IdentityReviewResult(
                company_id=staff.company_id, employee_id=staff.user_id,
                status=status, legacy_count=count,
                borrower_found=borrower, already_company_client=linked)
        except (httpx.HTTPError, ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise IdentityReviewUnavailable("Identity review could not be verified") from exc
