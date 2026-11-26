"""Opt-in attendance API; disabled unless explicitly configured."""
import secrets
from datetime import datetime
from uuid import UUID

import httpx
import psycopg
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .loanhub_staff_verifier import LoanHubStaffVerifier, StaffVerificationUnavailable
from .owner_staff_management_routes import fail, owner_context, call_loanhub
from .owner_attendance_inbox import OwnerAttendanceInbox
from .staff_registration_read_origin import safe_staff_read_origin
from .staff_login_routes import COOKIE, CSRF_COOKIE, NO_STORE, _config, _same_origin
from .staff_authorization import StaffAccessDenied
from .staff_attendance import AttendanceAction, AttendanceRejected
from .staff_attendance_store import AttendanceStore
from .staff_attendance_monitor_store import AttendanceMonitorStore
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


def _authorize_capture(payload: AttendanceCapture, request: Request, cfg):
    if not _same_origin(request, cfg.public_origin):
        return None, None, fail("FORBIDDEN_ORIGIN", 403)
    record = cfg.store.resolve(request.cookies.get(COOKIE, ""))
    if record is None:
        return None, None, fail("UNAUTHENTICATED", 401)
    csrf = request.headers.get("x-csrf-token", "")
    if (not csrf or not csrf.isascii()
            or request.cookies.get(CSRF_COOKIE) != csrf
            or not secrets.compare_digest(csrf, record.csrf_token)):
        return None, None, fail("CSRF_REJECTED", 403)
    try:
        base = cfg.verifier
        staff = LoanHubStaffVerifier(
            origin=cfg.loanhub_origin, public_key=base._public_key,
            batlokoa_company_id=base._company_id, client=base._client,
            allow_unverified_company_owner=False,
        ).verify(record.access_token)
    except StaffVerificationUnavailable:
        return None, None, fail("STAFF_VERIFICATION_REQUIRED", 403)
    if not (payload.branch_id in staff.branch_ids or
            (staff.company_wide_scope is True and
             staff.role in {"COMPANY_OWNER", "COMPANY_ADMIN"})):
        return None, None, fail("BRANCH_NOT_AUTHORIZED", 403)
    if payload.captured_at.utcoffset() is None:
        return None, None, fail("LOCATION_UNVERIFIED", 422)
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
            return None, None, fail("BRANCH_DIRECTORY_UNAVAILABLE", 503)
        data = response.json()
        if not isinstance(data, list) or len(data) > 100:
            return None, None, fail("BRANCH_DIRECTORY_UNAVAILABLE", 503)
        seen, active = set(), set()
        for item in data:
            if UUID(str(item["company_id"])) != staff.company_id:
                return None, None, fail("BRANCH_DIRECTORY_UNAVAILABLE", 503)
            identifier = UUID(str(item["id"]))
            if identifier in seen:
                return None, None, fail("BRANCH_DIRECTORY_UNAVAILABLE", 503)
            seen.add(identifier)
            if item.get("is_active") is True:
                active.add(identifier)
        if payload.branch_id not in active:
            return None, None, fail("BRANCH_NOT_AUTHORIZED", 403)
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        return None, None, fail("BRANCH_DIRECTORY_UNAVAILABLE", 503)
    return staff, ActiveBranch(staff.company_id, payload.branch_id, True), None


def _record(action: AttendanceAction, payload: AttendanceCapture, request: Request):
    store = getattr(request.app.state, "staff_attendance_store", None)
    cfg = _config(request)
    if (getattr(request.app.state, "staff_attendance_enabled", False) is not True
            or not isinstance(store, AttendanceStore) or cfg is None):
        return fail("ATTENDANCE_DISABLED", 503)
    staff, branch, denial = _authorize_capture(payload, request, cfg)
    if denial is not None:
        return denial
    try:
        session_id, event_id, event = store.record(
            staff, branch,
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


def _read(request: Request, *, open_only=False, limit=30, before=None):
    store = getattr(request.app.state, "staff_attendance_store", None)
    cfg = _config(request)
    if (getattr(request.app.state, "staff_attendance_enabled", False) is not True
            or not isinstance(store, AttendanceStore) or cfg is None):
        return fail("ATTENDANCE_DISABLED", 503)
    record = cfg.store.resolve(request.cookies.get(COOKIE, ""))
    if record is None:
        return fail("UNAUTHENTICATED", 401)
    try:
        base = cfg.verifier
        staff = LoanHubStaffVerifier(
            origin=cfg.loanhub_origin, public_key=base._public_key,
            batlokoa_company_id=base._company_id, client=base._client,
            allow_unverified_company_owner=False,
        ).verify(record.access_token)
    except StaffVerificationUnavailable:
        return fail("STAFF_VERIFICATION_REQUIRED", 403)
    try:
        rows = store.read_sessions(staff, open_only=open_only, limit=limit, before=before)
    except StaffAccessDenied:
        return fail("STAFF_VERIFICATION_REQUIRED", 403)
    except (psycopg.Error, ValueError):
        return fail("ATTENDANCE_UNAVAILABLE", 503)
    if open_only:
        return JSONResponse({"clocked_in": bool(rows),
                             "session": rows[0] if rows else None}, headers=NO_STORE)
    return JSONResponse({"sessions": rows,
                         "next_before": rows[-1]["session_id"] if len(rows) == limit else None},
                        headers=NO_STORE)


@router.get("/api/v1/staff/attendance/status", include_in_schema=False)
def attendance_status(request: Request):
    return _read(request, open_only=True, limit=1)


@router.get("/api/v1/staff/attendance/history", include_in_schema=False)
def attendance_history(request: Request, limit: int = Query(30, ge=1, le=100),
                       before: int | None = Query(None, gt=0, le=9223372036854775807)):
    return _read(request, limit=limit, before=before)


class MonitorCapture(AttendanceCapture):
    session_id: int = Field(gt=0, le=9223372036854775807, strict=True)


@router.post("/api/v1/staff/attendance/monitor", include_in_schema=False)
def monitor_attendance(payload: MonitorCapture, request: Request):
    cfg = _config(request)
    store = getattr(request.app.state, "staff_attendance_monitor_store", None)
    if (getattr(request.app.state, "staff_attendance_enabled", False) is not True
            or getattr(request.app.state, "staff_attendance_monitor_enabled", False) is not True
            or not isinstance(store, AttendanceMonitorStore) or cfg is None):
        return fail("MONITOR_DISABLED", 503)
    staff, branch, denial = _authorize_capture(payload, request, cfg)
    if denial is not None:
        return denial
    try:
        reading, state, alert = store.record(
            staff, branch, payload.session_id,
            Position(payload.latitude, payload.longitude, payload.accuracy_m),
            captured_at=payload.captured_at,
        )
    except StaffAccessDenied:
        return fail("BRANCH_NOT_AUTHORIZED", 403)
    except AttendanceRejected as exc:
        code = str(exc)
        if code in {"NO_ACTIVE_SESSION", "LOCATION_REPLAYED"}:
            return fail(code, 409)
        if code == "LOCATION_UNVERIFIED":
            return fail(code, 422)
        return fail("MONITOR_UNAVAILABLE", 503)
    except (psycopg.Error, ValueError):
        return fail("MONITOR_UNAVAILABLE", 503)
    return JSONResponse({
        "session_id": payload.session_id,
        "reading": reading.value,
        "last_confirmed": state.last_confirmed.value,
        "observed_at": state.last_observed_at.isoformat(),
        "transition_recorded": alert is not None,
    }, headers=NO_STORE)


def _owner_alert_labels(request, staff, token):
    def directory(path, max_bytes):
        response = call_loanhub(request, method="GET", path=path,
                                token=token, company_id=staff.company_id)
        if (response.status_code != 200 or len(response.content) > max_bytes
                or "application/json" not in response.headers.get("content-type", "").lower()):
            raise ValueError("Directory unavailable")
        rows = response.json()
        if not isinstance(rows, list) or len(rows) > 100:
            raise ValueError("Invalid directory")
        for row in rows:
            if UUID(str(row["company_id"])) != staff.company_id:
                raise ValueError("Directory scope mismatch")
        return rows

    employees, branches = {}, {}
    for item in directory("/api/v1/company-staff/?limit=100", 262144):
        user = item["user"]
        identifier = UUID(str(user["id"]))
        if item.get("user_id") is not None and UUID(str(item["user_id"])) != identifier:
            raise ValueError("User mismatch")
        if identifier in employees:
            raise ValueError("Ambiguous user")
        person = user.get("person") or {}
        first, last = person.get("first_name"), person.get("last_name")
        if any(value is not None and not isinstance(value, str) for value in (first, last)):
            raise ValueError("Invalid name")
        employees[identifier] = ((first or "") + " " + (last or "")).strip()[:200] or None
    for item in directory("/api/v1/branches/?limit=100", 131072):
        identifier = UUID(str(item["id"]))
        if identifier in branches or not isinstance(item["name"], str):
            raise ValueError("Invalid branch")
        branches[identifier] = item["name"].strip()[:120] or None
    return employees, branches


@router.get("/api/v1/staff/manage/attendance/alerts", include_in_schema=False)
def owner_attendance_alerts(request: Request,
                            after: int = Query(0, ge=0, le=9223372036854775807),
                            limit: int = Query(50, ge=1, le=100)):
    cfg = _config(request)
    inbox = getattr(request.app.state, "owner_attendance_inbox", None)
    if (getattr(request.app.state, "staff_attendance_enabled", False) is not True
            or getattr(request.app.state, "owner_attendance_inbox_enabled", False) is not True
            or not isinstance(inbox, OwnerAttendanceInbox) or cfg is None):
        return fail("OWNER_INBOX_DISABLED", 503)
    if not safe_staff_read_origin(request, cfg.public_origin):
        return fail("FORBIDDEN_ORIGIN", 403)
    record, staff, denial = owner_context(request, require_verified=True)
    if denial is not None:
        return denial
    try:
        result = inbox.read(staff, after=after, limit=limit)
    except StaffAccessDenied:
        return fail("OWNER_ONLY", 403)
    except (psycopg.Error, ValueError):
        return fail("OWNER_INBOX_UNAVAILABLE", 503)
    if result["alerts"]:
        # Attendance employee IDs are user UUIDs, NOT membership UUIDs.
        # Enrich only this authorized page with current directory labels.
        try:
            employees, branches = _owner_alert_labels(request, staff, record.access_token)
            for alert in result["alerts"]:
                alert["employee_name"] = employees.get(UUID(alert["employee_id"]))
                alert["branch_name"] = branches.get(UUID(alert["branch_id"]))
        except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
            # Never guess a name or use a partly validated directory.
            for alert in result["alerts"]:
                alert["employee_name"] = None
                alert["branch_name"] = None
    return JSONResponse(result, headers=NO_STORE)
