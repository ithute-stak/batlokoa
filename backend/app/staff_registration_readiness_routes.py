"""Non-activating LoanHub registration release readiness for Batlokoa.

This read-only endpoint exposes no borrower information, no write capability,
and no identity clearance. An upstream request always runs with the current
verified staff's signed LoanHub credential and company context.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .loanhub_staff_verifier import StaffVerificationUnavailable
from .staff_login_routes import COOKIE, NO_STORE, _config, _same_origin

router = APIRouter()
_ALLOWED_REASON = {"NEW_ONLY_REGISTRATION_NOT_RELEASED"}


@router.get("/api/v1/staff/clients/registration-readiness", include_in_schema=False)
async def registration_readiness(request: Request):
    config = _config(request)
    if config is None:
        return JSONResponse({"code": "REGISTRATION_UNAVAILABLE"}, status_code=503, headers=NO_STORE)
    if not _same_origin(request, config.public_origin):
        return JSONResponse({"code": "FORBIDDEN_ORIGIN"}, status_code=403, headers=NO_STORE)
    session_id = request.cookies.get(COOKIE, "")
    record = config.store.resolve(session_id)
    if record is None:
        return JSONResponse({"code": "UNAUTHENTICATED"}, status_code=401, headers=NO_STORE)
    try:
        staff = config.verifier.verify(record.access_token)
    except StaffVerificationUnavailable:
        config.store.revoke(session_id)
        return JSONResponse({"code": "UNAUTHENTICATED"}, status_code=401, headers=NO_STORE)

    # The upstream availability response is informational even if it
    # eventually changes; never infer write authorization from this endpoint.
    url = config.loanhub_origin.rstrip("/") + "/api/v1/batlokoa/registration/availability"
    try:
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=5.0) as client:
            response = client.get(
                url,
                headers={
                    "Authorization": "Bearer " + record.access_token,
                    "X-Company-ID": str(staff.company_id),
                    "X-Active-Role": staff.role.lower(),
                    "Accept": "application/json",
                    "Cache-Control": "no-store",
                },
            )
        if response.status_code != 200 or len(response.content) > 4096 or (
            "application/json" not in response.headers.get("content-type", "").lower()
        ):
            raise ValueError("Unapproved upstream availability response")
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("Invalid availability data")
        for key in (
            "new_only_registration_available",
            "can_submit_new_only_registration",
            "requires_identity_migration_approval",
            "requires_independent_release_approval",
        ):
            if type(body.get(key)) is not bool:
                raise ValueError("Missing strict availability flag")
        if body.get("reason_code") not in _ALLOWED_REASON:
            raise ValueError("Unknown registration release status")
        # Until the Batlokoa client creation handler is independently
        # reviewed, the BFF must never claim client creation is enabled.
        return JSONResponse(
            {
                "registration_available": False,
                "can_create_client": False,
                "reason_code": "NEW_ONLY_REGISTRATION_NOT_RELEASED",
                "requires_identity_migration_approval":
                    body["requires_identity_migration_approval"],
                "requires_independent_release_approval":
                    body["requires_independent_release_approval"],
            },
            headers=NO_STORE,
        )
    except (httpx.HTTPError, ValueError, TypeError, KeyError, UnicodeError):
        return JSONResponse(
            {"code": "REGISTRATION_READINESS_UNAVAILABLE"},
            status_code=503, headers=NO_STORE,
        )
