"""Read-only, authenticated LoanHub employer-group dropdown options.

No client data, no writes, no browser-supplied LoanHub credentials or tenants.
An upstream failure is never replaced by a fake static employer directory.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .loanhub_staff_verifier import StaffVerificationUnavailable
from .staff_login_routes import COOKIE, NO_STORE, _config

from .staff_registration_read_origin import safe_staff_read_origin

router = APIRouter()
_ALLOWED_ROLES = frozenset({
    "COMPANY_OWNER", "COMPANY_ADMIN", "BRANCH_MANAGER",
    "LOAN_OFFICER", "CREDIT_ANALYST",
})


def _fail(code: str, status: int) -> JSONResponse:
    return JSONResponse({"code": code}, status_code=status, headers=NO_STORE)


def _validated_employers(data):
    if not isinstance(data, list) or len(data) > 500:
        raise ValueError("Invalid employer directory")
    result = []
    seen = set()
    from uuid import UUID
    for item in data:
        if not isinstance(item, dict) or item.get("is_active") is not True:
            raise ValueError("Unexpected employer directory entry")
        identifier = str(UUID(str(item["id"])))
        code, name = item.get("code"), item.get("name")
        if (not isinstance(code, str) or not 1 <= len(code.strip()) <= 80
                or not isinstance(name, str) or not 1 <= len(name.strip()) <= 200
                or identifier in seen):
            raise ValueError("Invalid employer directory entry")
        seen.add(identifier)
        result.append({"id": identifier, "code": code.strip(), "name": name.strip()})
    return result


@router.get("/api/v1/staff/clients/registration-employers", include_in_schema=False)
def registration_employers(request: Request):
    cfg = _config(request)
    if cfg is None:
        return _fail("DIRECTORY_UNAVAILABLE", 503)
    if not safe_staff_read_origin(request, cfg.public_origin):
        return _fail("FORBIDDEN_ORIGIN", 403)
    cookie = request.cookies.get(COOKIE, "")
    record = cfg.store.resolve(cookie)
    if record is None:
        return _fail("UNAUTHENTICATED", 401)
    try:
        staff = cfg.verifier.verify(record.access_token)
    except StaffVerificationUnavailable:
        cfg.store.revoke(cookie)
        return _fail("UNAUTHENTICATED", 401)
    if (not staff.active or staff.role not in _ALLOWED_ROLES or
            (not staff.company_wide_scope and not staff.branch_ids) or
            (staff.company_wide_scope and staff.role not in
             {"COMPANY_OWNER", "COMPANY_ADMIN"})):
        return _fail("FORBIDDEN_STAFF_SCOPE", 403)
    try:
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=6) as client:
            response = client.get(
                cfg.loanhub_origin.rstrip("/") + "/api/v1/employer-groups?limit=500",
                headers={
                    "Authorization": "Bearer " + record.access_token,
                    "X-Company-ID": str(staff.company_id),
                    "X-Active-Role": staff.role.lower(),
                    "Accept": "application/json",
                    "Cache-Control": "no-store",
                },
            )
        if (response.status_code != 200 or len(response.content) > 262144
                or "application/json" not in response.headers.get(
                    "content-type", "").lower()):
            return _fail("DIRECTORY_UNAVAILABLE", 503)
        employers = _validated_employers(response.json())
        return JSONResponse({"employers": employers}, headers=NO_STORE)
    except (httpx.HTTPError, ValueError, TypeError, KeyError, UnicodeError):
        return _fail("DIRECTORY_UNAVAILABLE", 503)
