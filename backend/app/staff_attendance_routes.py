"""Opt-in attendance write API; not mounted or activated automatically."""
import secrets
from datetime import datetime
from uuid import UUID

import httpx
import psycopg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .loanhub_staff_verifier import LoanHubStaffVerifier, StaffVerificationUnavailable
from .owner_staff_management_routes import fail
from .staff_login_routes import COOKIE, CSRF_COOKIE, NO_STORE, _config, _same_origin
from .staff_authorization import StaffAccessDenied
from .staff_attendance import AttendanceAction, AttendanceRejected
from .staff_attendance_store import AttendanceStore
from .staff_branch_location import ActiveBranch
from .staff_geofence import Position

router = APIRouter()


class AttendanceCapture(BaseModel):
    branch_id: UUID
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False, strict=True)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False, strict=True)
    accuracy_m: float = Field(gt=0, allow_inf_nan=False, strict=True)
    captured_at: datetime
    model_config = {"extra": "forbid"}


def _record(action: AttendanceAction, payload: AttendanceCapture, request: Request):
    store = getattr(request.app.state, "staff_attendance_store", None)
    cfg = _config(request)
    if (getattr(request.app.state, "staff_attendance_enabled", False) is not True
            or not isinstance(store, AttendanceStore) or cfg is None):
        return fail("ATTENDANCE_DISABLED", 503)
    if not _same_origin(request, cfg.public_origin):
        return fail("FORBIDDEN_ORIGIN", 403)
    record = cfg.store.resolve(request.cookies.get(COOKIE, ""))
    if record is None:
        return fail("UNAUTHENTICATED", 401)
    csrf = request.headers.get("x-csrf-token", "")
    if (not csrf or not csrf.isascii()
            or request.cookies.get(CSRF_COOKIE) != csrf
            or not secrets.compare_digest(csrf, record.csrf_token)):
        return fail("CSRF_REJECTED", 403)
    try:
        base = cfg.verifier
        staff = LoanHubStaffVerifier(
            origin=cfg.loanhub_origin, public_key=base._public_key,
            batlokoa_company_id=base._company_id, client=base._client,
            allow_unverified_company_owner=False,
        ).verify(record.access_token)
    except StaffVerificationUnavailable:
        return fail("STAFF_VERIFICATION_REQUIRED", 403)
    if not (payload.branch_id in staff.branch_ids or
            (staff.company_wide_scope is True and
             staff.role in {"COMPANY_OWNER", "COMPANY_ADMIN"})):
        return fail("BRANCH_NOT_AUTHORIZED", 403)
    if payload.captured_at.utcoffset() is None:
        return fail("LOCATION_UNVERIFIED", 422)
    # Fetch the directory using the actual verified employee role, never an
    # elevated owner role or browser-supplied company header.
    try:
        with httpx.Client(trust_env=False, follow_redirects=False) as client:
            response = client.get(
                cfg.loanhub_origin.rstrip("/") + "/api/v1/branches/?limit=100",
                headers={"Authorization": "Bearer " + record.access_token,
                         "X-Company-ID": str(staff.company_id),
                         "X-Active-Role": staff.role.lower(),
                         "Accept": "application/json", "Cache-Control": "no-store"},
                timeout=8, follow_redirects=False,
            )
        if (response.status_code != 200 or len(response.content) > 131072
                or "application/json" not in response.headers.get("content-type", "").lower()):
            return fail("BRANCH_DIRECTORY_UNAVAILABLE", 503)
        data = response.json()
        if not isinstance(data, list) or len(data) > 100:
            return fail("BRANCH_DIRECTORY_UNAVAILABLE", 503)
        seen, active = set(), set()
        for item in data:
            if UUID(str(item["company_id"])) != staff.company_id:
                return fail("BRANCH_DIRECTORY_UNAVAILABLE", 503)
            identifier = UUID(str(item["id"]))
            if identifier in seen:
                return fail("BRANCH_DIRECTORY_UNAVAILABLE", 503)
            seen.add(identifier)
            if item.get("is_active") is True:
                active.add(identifier)
        if payload.branch_id not in active:
            return fail("BRANCH_NOT_AUTHORIZED", 403)
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        return fail("BRANCH_DIRECTORY_UNAVAILABLE", 503)
    try:
        session_id, event_id, event = store.record(
            staff, ActiveBranch(staff.company_id, payload.branch_id, True),
            Position(payload.latitude, payload.longitude, payload.accuracy_m),
            action, captured_at=payload.captured_at,
        )
    except StaffAccessDenied:
        return fail("BRANCH_NOT_AUTHORIZED", 403)
    except AttendanceRejected as exc:
        code = str(exc)
        if code in {"ALREADY_CLOCKED_IN", "NOT_CLOCKED_IN",
                    "CLOCK_OUT_AT_ORIGINAL_BRANCH", "SESSION_CHANGED"}:
            return fail(code, 409)
        if code in {"OUTSIDE_PERIMETER", "LOCATION_UNVERIFIED"}:
            return fail(code, 422)
        return fail("ATTENDANCE_UNAVAILABLE", 503)
    except (psycopg.Error, ValueError):
        return fail("ATTENDANCE_UNAVAILABLE", 503)
    return JSONResponse({
        "session_id": session_id, "event_id": event_id,
        "action": event.action.value, "recorded_at": event.recorded_at.isoformat(),
        "branch_id": str(event.branch_id),
    }, status_code=201, headers=NO_STORE)


@router.post("/api/v1/staff/attendance/clock-in", include_in_schema=False)
def clock_in(payload: AttendanceCapture, request: Request):
    return _record(AttendanceAction.CLOCK_IN, payload, request)


@router.post("/api/v1/staff/attendance/clock-out", include_in_schema=False)
def clock_out(payload: AttendanceCapture, request: Request):
    return _record(AttendanceAction.CLOCK_OUT, payload, request)
