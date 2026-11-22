"""Company owner staff management adapter.

Read operations use the existing limited Batlokoa pilot. Account creation
requires an additional operator opt-in, a *verified* LoanHub owner and CSRF.
Every operation is reauthorized by LoanHub with the original owner's token.
This module never accepts a company, role or bearer token from browser headers.
"""
from __future__ import annotations

import secrets
from uuid import UUID

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .loanhub_staff_verifier import LoanHubStaffVerifier, StaffVerificationUnavailable
from .staff_login_routes import (
    COOKIE, CSRF_COOKIE, NO_STORE, _config, _same_origin,
)

router = APIRouter()
ALLOWED_ROLES = frozenset({
    "BRANCH_MANAGER", "LOAN_OFFICER", "CREDIT_ANALYST",
    "COLLECTIONS_OFFICER", "FINANCE_OFFICER", "COMPANY_ADMIN",
})


class StaffAccountDraft(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=8, max_length=16, pattern=r"^\+?[0-9]{8,15}$")
    email: str | None = Field(default=None, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    role: str
    branch_id: UUID | None = None
    confirm: bool

    model_config = {"extra": "forbid"}


def fail(code: str, status: int) -> JSONResponse:
    return JSONResponse({"code": code}, status_code=status, headers=NO_STORE)


def owner_context(request: Request, *, require_verified: bool = False):
    cfg = _config(request)
    if cfg is None:
        return None, None, fail("STAFF_MANAGEMENT_DISABLED", 503)
    record = cfg.store.resolve(request.cookies.get(COOKIE, ""))
    if record is None:
        return None, None, fail("UNAUTHENTICATED", 401)
    try:
        if require_verified:
            base = cfg.verifier
            verifier = LoanHubStaffVerifier(
                origin=cfg.loanhub_origin, public_key=base._public_key,
                batlokoa_company_id=base._company_id,
                client=base._client,
                allow_unverified_company_owner=False,
            )
        else:
            verifier = cfg.verifier
        staff = verifier.verify(record.access_token)
    except StaffVerificationUnavailable:
        return None, None, fail("OWNER_VERIFICATION_REQUIRED" if require_verified
                                else "UNAUTHENTICATED", 403 if require_verified else 401)
    if staff.role != "COMPANY_OWNER" or not staff.company_wide_scope:
        return None, None, fail("OWNER_ONLY", 403)
    return record, staff, None


def call_loanhub(request: Request, *, method: str, path: str, token: str,
                 company_id: UUID, json_body: dict | None = None):
    cfg = _config(request)
    assert cfg is not None
    headers = {
        "Authorization": "Bearer " + token,
        "X-Company-ID": str(company_id),
        "X-Active-Role": "company_owner",
        "Accept": "application/json",
        "Cache-Control": "no-store",
    }
    if json_body is not None:
        headers["Content-Type"] = "application/json"
    with httpx.Client(trust_env=False, follow_redirects=False) as client:
        return client.request(
            method, cfg.loanhub_origin.rstrip("/") + path,
            headers=headers, json=json_body,
            timeout=8, follow_redirects=False,
        )


@router.get("/api/v1/staff/manage/branches", include_in_schema=False)
def owner_branches(request: Request):
    record, staff, denial = owner_context(request)
    if denial is not None:
        return denial
    try:
        response = call_loanhub(request, method="GET", path="/api/v1/branches/?limit=100",
                                token=record.access_token, company_id=staff.company_id)
        if response.status_code != 200 or len(response.content) > 131072:
            return fail("BRANCH_DIRECTORY_UNAVAILABLE", 503)
        data = response.json()
        if not isinstance(data, list) or len(data) > 100:
            return fail("BRANCH_DIRECTORY_UNAVAILABLE", 503)
        branches = []
        for item in data:
            if not isinstance(item, dict) or UUID(str(item["company_id"])) != staff.company_id:
                return fail("BRANCH_DIRECTORY_UNAVAILABLE", 503)
            if item.get("is_active") is not True:
                continue
            branches.append({"id": str(UUID(str(item["id"]))),
                             "name": str(item["name"])[:120]})
        return JSONResponse({"branches": branches}, headers=NO_STORE)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return fail("BRANCH_DIRECTORY_UNAVAILABLE", 503)


@router.get("/api/v1/staff/manage/members", include_in_schema=False)
def owner_members(request: Request):
    record, staff, denial = owner_context(request)
    if denial is not None:
        return denial
    try:
        response = call_loanhub(request, method="GET", path="/api/v1/company-staff/?limit=100",
                                token=record.access_token, company_id=staff.company_id)
        if response.status_code != 200 or len(response.content) > 262144:
            return fail("STAFF_DIRECTORY_UNAVAILABLE", 503)
        data = response.json()
        if not isinstance(data, list) or len(data) > 100:
            return fail("STAFF_DIRECTORY_UNAVAILABLE", 503)
        members = []
        for item in data:
            if not isinstance(item, dict) or UUID(str(item["company_id"])) != staff.company_id:
                return fail("STAFF_DIRECTORY_UNAVAILABLE", 503)
            user = item["user"]
            if not isinstance(user, dict):
                return fail("STAFF_DIRECTORY_UNAVAILABLE", 503)
            person = user.get("person") or {}
            if not isinstance(person, dict):
                return fail("STAFF_DIRECTORY_UNAVAILABLE", 503)
            first = str(person.get("first_name") or "")
            last = str(person.get("last_name") or "")
            members.append({
                "id": str(UUID(str(item["id"]))),
                "name": (first + " " + last).strip()[:200],
                "role": str(item["role"])[:60].upper(),
                "branch_id": str(UUID(str(item["branch_id"]))) if item.get("branch_id") else None,
                "active": item.get("is_active") is True,
                "verified": user.get("is_verified") is True,
            })
        return JSONResponse({"members": members}, headers=NO_STORE)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return fail("STAFF_DIRECTORY_UNAVAILABLE", 503)


@router.post("/api/v1/staff/manage/members", include_in_schema=False)
def owner_create_member(payload: StaffAccountDraft, request: Request):
    # Explicit independent operational release gate. Read-only pilot does
    # not automatically authorize privileged account writes.
    if getattr(request.app.state, "staff_account_creation_enabled", False) is not True:
        return fail("STAFF_CREATION_NOT_RELEASED", 503)
    cfg = _config(request)
    if cfg is None:
        return fail("STAFF_MANAGEMENT_DISABLED", 503)
    if not _same_origin(request, cfg.public_origin):
        return fail("FORBIDDEN_ORIGIN", 403)
    record, staff, denial = owner_context(request, require_verified=True)
    if denial is not None:
        return denial
    csrf = request.headers.get("x-csrf-token", "")
    if (not csrf or request.cookies.get(CSRF_COOKIE) != csrf
            or not secrets.compare_digest(csrf, record.csrf_token)):
        return fail("CSRF_REJECTED", 403)
    if not payload.confirm or payload.role not in ALLOWED_ROLES:
        return fail("INVALID_STAFF_REQUEST", 422)
    if payload.role != "COMPANY_ADMIN" and payload.branch_id is None:
        return fail("BRANCH_REQUIRED", 422)
    if payload.role == "COMPANY_ADMIN" and payload.branch_id is not None:
        return fail("INVALID_STAFF_REQUEST", 422)
    try:
        # Staff creation remains subject to LoanHub's company quota, duplicate
        # checks, tenant scope, user role restrictions and valid branch checks.
        response = call_loanhub(
            request, method="POST", path="/api/v1/company-staff/accounts",
            token=record.access_token, company_id=staff.company_id,
            json_body={
                "first_name": payload.first_name.strip(),
                "last_name": payload.last_name.strip(),
                "phone": payload.phone.strip(),
                "email": payload.email,
                "password": payload.password,
                "role": payload.role.lower(),
                "branch_id": str(payload.branch_id) if payload.branch_id else None,
                "is_primary": True,
                "is_active": True,
            },
        )
        if response.status_code == 201:
            if len(response.content) > 32768:
                return fail("STAFF_CREATION_UNCONFIRMED", 503)
            created = response.json()
            if UUID(str(created["company_id"])) != staff.company_id:
                return fail("STAFF_CREATION_UNCONFIRMED", 503)
            return JSONResponse({
                "created": True,
                "staff_id": str(UUID(str(created["id"]))),
                "requires_verification": True,
            }, status_code=201, headers=NO_STORE)
        if response.status_code == 409:
            return fail("STAFF_ALREADY_EXISTS_OR_LIMIT", 409)
        if response.status_code in {400, 403, 422}:
            return fail("STAFF_CREATION_DENIED", 403)
        return fail("STAFF_CREATION_UNAVAILABLE", 503)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return fail("STAFF_CREATION_UNCONFIRMED", 503)
