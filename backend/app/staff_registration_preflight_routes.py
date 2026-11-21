"""Opt-in staff registration validation only; NEVER creates borrower records.

No upstream write, search, reservation or identity-clearance claim is made.
Response deliberately excludes all supplied client personal information.
"""
from __future__ import annotations

import json
import secrets
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError

from .loanhub_staff_verifier import StaffVerificationUnavailable
from .loanhub_registration_review import (
    LoanHubRegistrationReview, RegistrationIdentityReviewUnavailable,
)
from .staff_authorization import StaffAccessDenied
from .staff_client_registration import (
    ClientRegistrationDraft, prepare_client_registration,
)
from .staff_login_routes import (
    COOKIE, CSRF_COOKIE, NO_STORE, _config, _same_origin,
)

router = APIRouter()


class RegistrationPreflightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=8, max_length=30)
    date_of_birth: date
    gender: str = Field(min_length=1, max_length=100)
    district: str = Field(min_length=1, max_length=100)
    employment_status: str = Field(min_length=1, max_length=100)
    branch_id: UUID
    national_id: str | None = Field(default=None, max_length=100)
    passport_number: str | None = Field(default=None, max_length=100)
    monthly_income: str | None = Field(default=None, max_length=100)
    consent_to_share_profile: StrictBool = False
    consent_to_credit_checks: StrictBool = False


def _deny(code: str, status: int) -> JSONResponse:
    return JSONResponse({"code": code}, status_code=status, headers=NO_STORE)


@router.post("/api/v1/staff/clients/registration-preflight", include_in_schema=False)
async def registration_preflight(request: Request):
    cfg = _config(request)
    if (
        cfg is None or
        getattr(request.app.state, "staff_registration_preflight_enabled", False) is not True
    ):
        return _deny("REGISTRATION_PREFLIGHT_DISABLED", 503)
    if not _same_origin(request, cfg.public_origin):
        return _deny("FORBIDDEN_ORIGIN", 403)
    cookie = request.cookies.get(COOKIE, "")
    record = cfg.store.resolve(cookie)
    if record is None:
        return _deny("UNAUTHENTICATED", 401)
    csrf = request.headers.get("x-csrf-token", "")
    if (
        not csrf or
        not secrets.compare_digest(csrf, record.csrf_token) or
        request.cookies.get(CSRF_COOKIE) != csrf
    ):
        return _deny("CSRF_REJECTED", 403)
    # Verify the staff token before parsing potentially sensitive client data.
    try:
        identity = cfg.verifier.verify(record.access_token)
    except StaffVerificationUnavailable:
        cfg.store.revoke(cookie)
        return _deny("UNAUTHENTICATED", 401)

    if "application/json" not in request.headers.get("content-type", "").lower():
        return _deny("INVALID_REGISTRATION_DRAFT", 415)
    if request.headers.get("content-length") is not None:
        try:
            if int(request.headers["content-length"]) > 8192:
                return _deny("REGISTRATION_DRAFT_TOO_LARGE", 413)
        except ValueError:
            return _deny("INVALID_REGISTRATION_DRAFT", 422)
    raw = await request.body()
    if len(raw) > 8192:
        return _deny("REGISTRATION_DRAFT_TOO_LARGE", 413)
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Object required")
        payload = RegistrationPreflightRequest.model_validate(data)
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError, ValueError):
        # Never reflect input into FastAPI's default field-error payload.
        return _deny("INVALID_REGISTRATION_DRAFT", 422)
    try:
        result = prepare_client_registration(
            staff=identity,
            draft=ClientRegistrationDraft(**payload.model_dump()),
        )
    except StaffAccessDenied:
        return _deny("FORBIDDEN_STAFF_SCOPE", 403)
    except (ValueError, TypeError):
        return _deny("INVALID_REGISTRATION_DRAFT", 422)

    # This is merely syntax/authorization validation, not deduplication.
    # Never echo national ID, phone, birthdate, salary or name into responses.
    if result.can_submit is not False or result.identity_review_required is not True:
        return _deny("REGISTRATION_WRITES_NOT_AUTHORIZED", 503)

    identity_review = {
        "status": "not_checked",
        "decision": "human_review_required",
        "identity_match_found": None,
        "legacy_capture_found": None,
        "requires_human_review": True,
        "can_commit": False,
    }
    review_adapter = getattr(request.app.state, "staff_registration_identity_review", None)
    review_enabled = getattr(
        request.app.state, "staff_registration_identity_review_enabled", False
    ) is True
    if review_enabled:
        # Never silently substitute a different lookup, nor treat a passport
        # as a national ID. A separate trusted passport review is required.
        if (
            not isinstance(review_adapter, LoanHubRegistrationReview)
            or review_adapter._origin != cfg.loanhub_origin.rstrip("/")
        ):
            return _deny("IDENTITY_REVIEW_UNAVAILABLE", 503)
        if not payload.national_id or not payload.national_id.strip():
            identity_review["status"] = "unsupported_identity_document"
        else:
            try:
                reviewed = review_adapter.review(
                    staff=identity, access_token=record.access_token,
                    branch_id=payload.branch_id,
                    national_id=payload.national_id,
                )
            except StaffAccessDenied:
                return _deny("FORBIDDEN_STAFF_SCOPE", 403)
            except (RegistrationIdentityReviewUnavailable, ValueError, TypeError):
                return _deny("IDENTITY_REVIEW_UNAVAILABLE", 503)
            identity_review = {
                "status": "advisory_review_completed",
                "decision": reviewed.decision,
                "identity_match_found": reviewed.identity_match_found,
                "legacy_capture_found": reviewed.legacy_capture_found,
                "requires_human_review": True,
                "can_commit": False,
            }
    return JSONResponse({
        "validated": True,
        "identity_review_required": True,
        "can_submit": False,
        "company_id": str(result.company_id),
        "branch_id": str(result.branch_id),
        "reasons": list(result.reasons),
        "identity_review": identity_review,
    }, headers=NO_STORE)
