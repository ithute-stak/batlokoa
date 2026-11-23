"""Read-only branch labels from LoanHub, filtered to server-verified staff scope."""
from __future__ import annotations

from uuid import UUID
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .loanhub_staff_verifier import StaffVerificationUnavailable
from .staff_login_routes import COOKIE, NO_STORE, _config
from .staff_registration_employer_routes import _ALLOWED_ROLES, _fail
from .staff_registration_read_origin import safe_staff_read_origin

router = APIRouter()


def _verified_branches(data, staff):
    if not isinstance(data, list) or len(data) > 100:
        raise ValueError("Unexpected branch directory")
    result = []
    seen = set()
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Invalid branch")
        company_id = UUID(str(item["company_id"]))
        branch_id = UUID(str(item["id"]))
        name = item.get("name")
        if company_id != staff.company_id:
            raise ValueError("Cross-company branch in upstream response")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
            raise ValueError("Invalid branch name")
        if branch_id in seen:
            raise ValueError("Duplicate branch")
        seen.add(branch_id)
        if item.get("is_active") is not True:
            continue
        if staff.company_wide_scope or branch_id in staff.branch_ids:
            result.append({"id": str(branch_id), "name": name.strip()})
    return result


@router.get("/api/v1/staff/clients/registration-branches", include_in_schema=False)
def registration_branches(request: Request):
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
                cfg.loanhub_origin.rstrip("/") + "/api/v1/branches/?limit=100",
                headers={
                    "Authorization": "Bearer " + record.access_token,
                    "X-Company-ID": str(staff.company_id),
                    "X-Active-Role": staff.role.lower(),
                    "Accept": "application/json",
                    "Cache-Control": "no-store",
                },
            )
        if (response.status_code != 200 or len(response.content) > 131072
                or "application/json" not in response.headers.get(
                    "content-type", "").lower()):
            return _fail("DIRECTORY_UNAVAILABLE", 503)
        branches = _verified_branches(response.json(), staff)
        return JSONResponse({"branches": branches}, headers=NO_STORE)
    except (httpx.HTTPError, ValueError, TypeError, KeyError, UnicodeError):
        return _fail("DIRECTORY_UNAVAILABLE", 503)
