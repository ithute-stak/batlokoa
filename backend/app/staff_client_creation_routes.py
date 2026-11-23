"""Draft Save Client BFF handler for Batlokoa staff.

This module is NOT mounted on the live FastAPI app. The hard-coded release
gate is false and cannot be enabled with an HTTP field or environment variable.
Before release, replace this with an audited server-side authorization decision
only after LoanHub actually enables its protected new-only POST route.
"""
from __future__ import annotations

import json
import secrets
from uuid import UUID

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .loanhub_new_only_client_creation import (
    ClientCreationNotReleased, ClientCreationUnavailable,
    post_new_only_client,
)
from .loanhub_staff_verifier import StaffVerificationUnavailable
from .staff_authorization import StaffAccessDenied
from .staff_login_routes import (
    COOKIE, CSRF_COOKIE, NO_STORE, _config, _same_origin,
)

router = APIRouter()


def _release_approved() -> bool:
    return False


def _deny(code: str, status_code: int) -> JSONResponse:
    return JSONResponse({"code": code}, status_code=status_code, headers=NO_STORE)


@router.post("/api/v1/staff/clients/register", include_in_schema=False)
async def register_client(request: Request):
    cfg = _config(request)
    if cfg is None:
        return _deny("REGISTRATION_UNAVAILABLE", 503)
    if not _same_origin(request, cfg.public_origin):
        return _deny("FORBIDDEN_ORIGIN", 403)
    # Before release, do NOT parse or store customer PII or call LoanHub.
    if not _release_approved():
        return _deny("NEW_ONLY_REGISTRATION_NOT_RELEASED", 503)

    session_id = request.cookies.get(COOKIE, "")
    record = cfg.store.resolve(session_id)
    if record is None:
        return _deny("UNAUTHENTICATED", 401)
    csrf = request.headers.get("x-csrf-token", "")
    if (not csrf or not secrets.compare_digest(csrf, record.csrf_token)
            or request.cookies.get(CSRF_COOKIE) != csrf):
        return _deny("CSRF_REJECTED", 403)
    try:
        staff = cfg.verifier.verify(record.access_token)
    except StaffVerificationUnavailable:
        cfg.store.revoke(session_id)
        return _deny("UNAUTHENTICATED", 401)
    if "application/json" not in request.headers.get("content-type", "").lower():
        return _deny("INVALID_REGISTRATION", 415)
    if request.headers.get("content-length") is not None:
        try:
            if int(request.headers["content-length"]) > 32768:
                return _deny("REGISTRATION_TOO_LARGE", 413)
        except ValueError:
            return _deny("INVALID_REGISTRATION", 422)
    raw = await request.body()
    if len(raw) > 32768:
        return _deny("REGISTRATION_TOO_LARGE", 413)
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Object required")
        branch_id = UUID(payload["branch_id"])
        key = request.headers.get("idempotency-key", "")
        # Transport validates company boundary and rejects browser role claims.
        with httpx.Client(trust_env=False, follow_redirects=False) as client:
            result = post_new_only_client(
                staff=staff,
                branch_id=branch_id,
                loanhub_origin=cfg.loanhub_origin,
                loanhub_access_token=record.access_token,
                complete_payload=payload,
                idempotency_key=key,
                client=client,
                independently_approved_release=_release_approved(),
            )
    except (ValueError, TypeError, KeyError, UnicodeDecodeError,
            json.JSONDecodeError):
        return _deny("INVALID_REGISTRATION", 422)
    except StaffAccessDenied:
        return _deny("FORBIDDEN_STAFF_SCOPE", 403)
    except (ClientCreationNotReleased, ClientCreationUnavailable, httpx.HTTPError):
        return _deny("REGISTRATION_NOT_CONFIRMED", 503)
    return JSONResponse({
        "registered": True,
        "client_account_id": str(result.account_id),
        "replayed": result.replayed,
    }, status_code=201, headers=NO_STORE)
