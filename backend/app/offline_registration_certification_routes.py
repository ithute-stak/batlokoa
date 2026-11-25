"""Offline-only Batlokoa Save Client gateway certification route.

NOT imported by backend.app.main; never mounted on the live gateway.
Use only in a separately constructed, explicitly acknowledged sandbox test app.
All live registration UI controls remain submit-disabled.
"""
from __future__ import annotations

import json
import os
import re
import secrets
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .loanhub_staff_verifier import StaffVerificationUnavailable
from .staff_authorization import (
    StaffAccessDenied, StaffPermission, require_staff_permission,
)
from .staff_login_routes import (
    COOKIE, CSRF_COOKIE, NO_STORE, _config, _same_origin,
)

router = APIRouter()
_ACK = "BATLOKOA_OFFLINE_REGISTRATION_ACK"
_EXPECTED_ACK = "disposable_sandbox_only"
_ALLOWED_UPSTREAM_HOSTS = frozenset({
    "sandbox.loanhub.co.ls", "loanhub-offline.example",
})
_DISALLOWED_CLAIMS = frozenset({
    "company_id", "user_id", "role", "is_platform_admin",
    "independently_approved_release", "registered", "client_account_id",
})
_MAX_REQUEST_BYTES = 32768
_MAX_CONFIRMATION_BYTES = 4096
_KEY = re.compile(r"[A-Za-z0-9_.-]{16,128}")


def _deny(code: str, status: int) -> JSONResponse:
    return JSONResponse({"code": code}, status_code=status, headers=NO_STORE)


def _strict_pairs(pairs):
    """Refuse ambiguous JSON objects at every nesting level."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Repeated registration JSON field")
        result[key] = value
    return result


def _reject_nonfinite(_value):
    raise ValueError("Non-finite registration number")


def _is_json_content_type(value: str) -> bool:
    """Only the JSON media type, not a substring or lookalike, is accepted."""
    return value.split(";", 1)[0].strip().lower() == "application/json"


def _authorized_offline_upstream(origin: str) -> bool:
    parts = urlsplit(origin)
    return (
        parts.scheme == "https"
        and parts.hostname in _ALLOWED_UPSTREAM_HOSTS
        and parts.username is None and parts.password is None
        and parts.port in (None, 443)
        and parts.path in ("", "/") and not parts.query and not parts.fragment
    )


@router.post("/api/v1/staff/clients/register", include_in_schema=False)
async def register_client_offline(request: Request):
    """Sandbox-only BFF transport to the independently staged LoanHub route."""
    cfg = _config(request)
    if (
        cfg is None or
        os.environ.get(_ACK) != _EXPECTED_ACK or
        not _authorized_offline_upstream(cfg.loanhub_origin)
    ):
        return _deny("OFFLINE_REGISTRATION_UNAVAILABLE", 503)
    if not _same_origin(request, cfg.public_origin):
        return _deny("FORBIDDEN_ORIGIN", 403)
    session_id = request.cookies.get(COOKIE, "")
    record = cfg.store.resolve(session_id)
    if record is None:
        return _deny("UNAUTHENTICATED", 401)
    csrf = request.headers.get("x-csrf-token", "")
    if (
        not csrf or not secrets.compare_digest(csrf, record.csrf_token)
        or request.cookies.get(CSRF_COOKIE) != csrf
    ):
        return _deny("CSRF_REJECTED", 403)
    try:
        staff = cfg.verifier.verify(record.access_token)
    except StaffVerificationUnavailable:
        cfg.store.revoke(session_id)
        return _deny("UNAUTHENTICATED", 401)
    if not _is_json_content_type(request.headers.get("content-type", "")):
        return _deny("INVALID_REGISTRATION", 415)
    key = request.headers.get("idempotency-key", "")
    if not _KEY.fullmatch(key):
        return _deny("INVALID_IDEMPOTENCY_KEY", 422)
    try:
        size = request.headers.get("content-length")
        if size is not None and int(size) > _MAX_REQUEST_BYTES:
            return _deny("REGISTRATION_TOO_LARGE", 413)
        raw = await request.body()
        if len(raw) > _MAX_REQUEST_BYTES:
            return _deny("REGISTRATION_TOO_LARGE", 413)
        payload = json.loads(
            raw, object_pairs_hook=_strict_pairs,
            parse_constant=_reject_nonfinite,
        )
        if not isinstance(payload, dict) or (
            _DISALLOWED_CLAIMS.intersection(payload)
        ):
            return _deny("INVALID_REGISTRATION", 422)
        if not isinstance(payload.get("branch_id"), str):
            return _deny("INVALID_REGISTRATION", 422)
        branch_id = UUID(payload["branch_id"])
    except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError):
        return _deny("INVALID_REGISTRATION", 422)
    try:
        require_staff_permission(
            staff,
            expected_company_id=staff.company_id,
            branch_id=branch_id,
            permission=StaffPermission.REGISTER_CLIENT,
        )
    except StaffAccessDenied:
        return _deny("FORBIDDEN_STAFF_SCOPE", 403)

    headers = {
        "Authorization": "Bearer " + record.access_token,
        "X-Company-ID": str(staff.company_id),
        "X-Active-Role": staff.role.lower(),
        "Idempotency-Key": key,
        "Accept": "application/json",
        "Cache-Control": "no-store",
    }
    url = cfg.loanhub_origin.rstrip("/") + "/api/v1/batlokoa/registration/clients"
    try:
        if cfg.client is None:
            with httpx.Client(
                trust_env=False, follow_redirects=False, timeout=10.0,
            ) as client:
                upstream = client.post(
                    url, json=payload, headers=headers,
                )
        else:
            upstream = cfg.client.post(
                url, json=payload, headers=headers,
                timeout=10.0, follow_redirects=False,
            )
        if upstream.status_code != 201:
            if upstream.status_code in (409, 422):
                return _deny("REGISTRATION_REJECTED", upstream.status_code)
            if upstream.status_code in (401, 403):
                return _deny("REGISTRATION_UNAUTHORIZED", 403)
            return _deny("REGISTRATION_UNAVAILABLE", 503)
        if (
            len(upstream.content) > _MAX_CONFIRMATION_BYTES or
            not _is_json_content_type(
                upstream.headers.get("content-type", "")
            )
        ):
            return _deny("UNTRUSTED_REGISTRATION_RECEIPT", 503)
        receipt = json.loads(
            upstream.content, object_pairs_hook=_strict_pairs,
            parse_constant=_reject_nonfinite,
        )
        if not isinstance(receipt, dict) or set(receipt) != {
            "registered", "client_account_id", "replayed",
        } or receipt["registered"] is not True or (
            type(receipt["replayed"]) is not bool
        ):
            return _deny("UNTRUSTED_REGISTRATION_RECEIPT", 503)
        if not isinstance(receipt["client_account_id"], str):
            return _deny("UNTRUSTED_REGISTRATION_RECEIPT", 503)
        try:
            client_id = UUID(receipt["client_account_id"])
        except ValueError:
            return _deny("UNTRUSTED_REGISTRATION_RECEIPT", 503)
        if str(client_id) != receipt["client_account_id"].lower():
            return _deny("UNTRUSTED_REGISTRATION_RECEIPT", 503)
        return JSONResponse({
            "registered": True,
            "client_account_id": str(client_id),
            "replayed": receipt["replayed"],
        }, status_code=201, headers=NO_STORE)
    except (httpx.HTTPError, ValueError, TypeError, KeyError, UnicodeError):
        return _deny("REGISTRATION_UNAVAILABLE", 503)
