"""National-ID-first registration gate.

A protected read-only lookup against LoanHub's existing registration-review.
Never sends an ID via URL, echoes IDs, creates a borrower, or grants final
registration clearance. Duplicate/legacy matches block new-only capture.
"""
from __future__ import annotations

import json
import secrets
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .loanhub_registration_review import (
    LoanHubRegistrationReview, RegistrationIdentityReviewUnavailable,
)
from .loanhub_staff_verifier import StaffVerificationUnavailable
from .staff_authorization import StaffAccessDenied
from .staff_login_routes import COOKIE, CSRF_COOKIE, NO_STORE, _config, _same_origin

router = APIRouter()


class NationalIdCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    national_id: str = Field(min_length=4, max_length=100)
    branch_id: UUID


def deny(code: str, status: int) -> JSONResponse:
    return JSONResponse({"code": code}, status_code=status, headers=NO_STORE)


@router.post("/api/v1/staff/clients/national-id-check", include_in_schema=False)
async def national_id_check(request: Request):
    cfg = _config(request)
    adapter = getattr(request.app.state, "staff_registration_identity_review", None)
    if (cfg is None or
        getattr(request.app.state, "staff_registration_identity_review_enabled", False)
            is not True or
        not isinstance(adapter, LoanHubRegistrationReview) or
        adapter._origin != cfg.loanhub_origin.rstrip("/")):
        return deny("IDENTITY_CHECK_DISABLED", 503)
    if not _same_origin(request, cfg.public_origin):
        return deny("FORBIDDEN_ORIGIN", 403)
    cookie = request.cookies.get(COOKIE, "")
    record = cfg.store.resolve(cookie)
    if record is None:
        return deny("UNAUTHENTICATED", 401)
    csrf = request.headers.get("x-csrf-token", "")
    if (not csrf or
        not secrets.compare_digest(csrf, record.csrf_token) or
        request.cookies.get(CSRF_COOKIE) != csrf):
        return deny("CSRF_REJECTED", 403)
    try:
        identity = cfg.verifier.verify(record.access_token)
    except StaffVerificationUnavailable:
        cfg.store.revoke(cookie)
        return deny("UNAUTHENTICATED", 401)
    if "application/json" not in request.headers.get("content-type", "").lower():
        return deny("INVALID_REQUEST", 415)
    if request.headers.get("content-length"):
        try:
            if int(request.headers["content-length"]) > 1024:
                return deny("INVALID_REQUEST", 413)
        except ValueError:
            return deny("INVALID_REQUEST", 422)
    raw = await request.body()
    if len(raw) > 1024:
        return deny("INVALID_REQUEST", 413)
    try:
        body = json.loads(raw)
        payload = NationalIdCheck.model_validate(body)
        national_id = payload.national_id.strip()
        if len(national_id) < 4 or len(national_id) > 100:
            return deny("INVALID_REQUEST", 422)
    except (json.JSONDecodeError, UnicodeError, ValidationError, ValueError, TypeError):
        return deny("INVALID_REQUEST", 422)
    try:
        result = adapter.review(
            staff=identity,
            access_token=record.access_token,
            branch_id=payload.branch_id,
            national_id=national_id,
        )
    except StaffAccessDenied:
        return deny("FORBIDDEN_STAFF_SCOPE", 403)
    except (RegistrationIdentityReviewUnavailable, ValueError, TypeError):
        return deny("IDENTITY_CHECK_UNAVAILABLE", 503)

    possible_match = (
        result.identity_match_found or result.legacy_capture_found
        or result.decision != "new_identity_candidate"
    )
    # No identity, names, loan exposures, or cross-tenant record identifiers.
    # A 'new candidate' is not proof of uniqueness, authorization or consent.
    return JSONResponse({
        "status": "existing_or_review" if possible_match else "candidate_only",
        "may_continue_preparation": not possible_match,
        "registration_authorized": False,
        "human_review_required": True,
    }, headers=NO_STORE)
