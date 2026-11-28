"""Opt-in attendance API; disabled unless explicitly configured."""
import secrets
from datetime import date, datetime, time
from typing import Literal
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
from .staff_authorization import StaffAccessDenied, VerifiedStaffIdentity
from .staff_morning_work_roster_store import MorningWorkRosterStore
from .staff_attendance_notification_inbox import AttendanceNotificationInbox
from .staff_morning_reminder import LESOTHO
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


@router.get("/api/v1/staff/manage/attendance/access-events", include_in_schema=False)
def owner_attendance_access_events(request: Request,
                                   before_at: datetime | None = Query(None),
                                   before_id: UUID | None = Query(None),
                                   limit: int = Query(50, ge=1, le=100)):
    cfg = _config(request)
    inbox = getattr(request.app.state, "owner_attendance_inbox", None)
    if (getattr(request.app.state, "staff_attendance_enabled", False) is not True
            or getattr(request.app.state, "owner_attendance_inbox_enabled", False) is not True
            or getattr(request.app.state, "owner_access_inbox_enabled", False) is not True
            or not isinstance(inbox, OwnerAttendanceInbox) or cfg is None):
        return fail("OWNER_ACCESS_INBOX_DISABLED", 503)
    if not safe_staff_read_origin(request, cfg.public_origin):
        return fail("FORBIDDEN_ORIGIN", 403)
    record, staff, denial = owner_context(request, require_verified=True)
    if denial is not None:
        return denial
    if ((before_at is None) != (before_id is None)
            or (before_at is not None and before_at.utcoffset() is None)):
        return fail("INVALID_ACCESS_CURSOR", 422)
    try:
        result = inbox.read_access_events(staff, before_at=before_at,
                                          before_id=before_id, limit=limit)
    except StaffAccessDenied:
        return fail("OWNER_ONLY", 403)
    except (psycopg.Error, ValueError):
        return fail("OWNER_INBOX_UNAVAILABLE", 503)
    if result["events"]:
        try:
            employees, branches = _owner_alert_labels(request, staff, record.access_token)
            for event in result["events"]:
                event["employee_name"] = employees.get(UUID(event["employee_id"]))
                event["branch_name"] = (branches.get(UUID(event["branch_id"]))
                                        if event["branch_id"] is not None else None)
        except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
            for event in result["events"]:
                event["employee_name"] = None
                event["branch_name"] = None
    return JSONResponse(result, headers=NO_STORE)


class WorkRosterDraft(BaseModel):
    employee_id: UUID
    work_date: date
    scheduled_to_work: bool = Field(strict=True)
    model_config = {"extra": "forbid"}


def _roster_context(request, *, write=False):
    cfg = _config(request)
    store = getattr(request.app.state, "staff_morning_work_roster_store", None)
    if (cfg is None or not isinstance(store, MorningWorkRosterStore)
            or getattr(request.app.state, "staff_attendance_enabled", False) is not True
            or getattr(request.app.state, "owner_work_roster_enabled", False) is not True):
        return None, None, None, fail("WORK_ROSTER_DISABLED", 503)
    origin_ok = (_same_origin(request, cfg.public_origin) if write
                 else safe_staff_read_origin(request, cfg.public_origin))
    if not origin_ok:
        return None, None, None, fail("FORBIDDEN_ORIGIN", 403)
    record, staff, denial = owner_context(request, require_verified=True)
    if denial is not None:
        return None, None, None, denial
    if write:
        csrf = request.headers.get("x-csrf-token", "")
        if (not csrf or not csrf.isascii()
                or request.cookies.get(CSRF_COOKIE) != csrf
                or not secrets.compare_digest(csrf, record.csrf_token)):
            return None, None, None, fail("CSRF_REJECTED", 403)
    return store, record, staff, None


@router.get("/api/v1/staff/manage/attendance/work-roster", include_in_schema=False)
def owner_work_roster(request: Request, work_date: date,
                      after: UUID | None = Query(None),
                      limit: int = Query(50, ge=1, le=100)):
    store, _, staff, denial = _roster_context(request)
    if denial is not None:
        return denial
    try:
        result = store.read_day(staff, work_date=work_date, after=after, limit=limit)
    except StaffAccessDenied:
        return fail("OWNER_ONLY", 403)
    except (psycopg.Error, ValueError):
        return fail("WORK_ROSTER_UNAVAILABLE", 503)
    return JSONResponse(result, headers=NO_STORE)


@router.post("/api/v1/staff/manage/attendance/work-roster", include_in_schema=False)
def owner_set_work_roster(payload: WorkRosterDraft, request: Request):
    store, record, staff, denial = _roster_context(request, write=True)
    if denial is not None:
        return denial
    try:
        response = call_loanhub(request, method="GET",
            path="/api/v1/company-staff/?limit=100", token=record.access_token,
            company_id=staff.company_id)
        if (response.status_code != 200 or len(response.content)>262144
                or "application/json" not in response.headers.get("content-type", "").lower()):
            return fail("STAFF_DIRECTORY_UNAVAILABLE", 503)
        rows = response.json()
        if not isinstance(rows, list) or len(rows)>100:
            return fail("STAFF_DIRECTORY_UNAVAILABLE", 503)
        matches = []
        for row in rows:
            if UUID(str(row["company_id"])) != staff.company_id:
                return fail("STAFF_DIRECTORY_UNAVAILABLE", 503)
            user = row["user"]
            user_id = UUID(str(user["id"]))
            if row.get("user_id") is not None and UUID(str(row["user_id"])) != user_id:
                return fail("STAFF_DIRECTORY_UNAVAILABLE", 503)
            if user_id == payload.employee_id:
                matches.append(row)
        if len(matches) != 1:
            return fail("EMPLOYEE_NOT_VERIFIED", 403)
        member = matches[0]
        if member.get("is_active") is not True:
            return fail("EMPLOYEE_NOT_VERIFIED", 403)
        # Only the target's verified membership fields are needed by the store.
        employee = VerifiedStaffIdentity(payload.employee_id, staff.company_id,
            str(member["role"]).upper(), True, frozenset())
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        return fail("STAFF_DIRECTORY_UNAVAILABLE", 503)
    try:
        changed = store.set_day(staff, employee, work_date=payload.work_date,
                                scheduled_to_work=payload.scheduled_to_work)
    except StaffAccessDenied:
        return fail("EMPLOYEE_NOT_VERIFIED", 403)
    except ValueError:
        return fail("INVALID_WORK_ROSTER_DATE", 422)
    except psycopg.Error:
        return fail("WORK_ROSTER_UNAVAILABLE", 503)
    return JSONResponse({"changed": changed, "employee_id": str(employee.user_id),
                         "work_date": payload.work_date.isoformat(),
                         "scheduled_to_work": payload.scheduled_to_work}, headers=NO_STORE)


@router.get("/api/v1/staff/manage/attendance/work-roster/employees", include_in_schema=False)
def owner_work_roster_employees(request: Request):
    _, record, staff, denial = _roster_context(request)
    if denial is not None:
        return denial
    try:
        response = call_loanhub(request, method="GET",
            path="/api/v1/company-staff/?limit=100", token=record.access_token,
            company_id=staff.company_id)
        if (response.status_code != 200 or len(response.content) > 262144
                or "application/json" not in response.headers.get("content-type", "").lower()):
            return fail("STAFF_DIRECTORY_UNAVAILABLE", 503)
        rows = response.json()
        if not isinstance(rows, list) or len(rows) >= 100:
            # A full upstream page may be truncated. Do not imply completeness.
            return fail("STAFF_DIRECTORY_UNAVAILABLE", 503)
        seen, employees = set(), []
        for row in rows:
            if UUID(str(row["company_id"])) != staff.company_id:
                return fail("STAFF_DIRECTORY_UNAVAILABLE", 503)
            user = row["user"]
            identifier = UUID(str(user["id"]))
            if (identifier in seen or
                    (row.get("user_id") is not None and UUID(str(row["user_id"])) != identifier)):
                return fail("STAFF_DIRECTORY_UNAVAILABLE", 503)
            seen.add(identifier)
            role = row["role"]
            if not isinstance(role, str) or type(row.get("is_active")) is not bool:
                return fail("STAFF_DIRECTORY_UNAVAILABLE", 503)
            role = role.upper()
            if not row["is_active"] or role not in {
                    "COMPANY_OWNER", "COMPANY_ADMIN", "BRANCH_MANAGER",
                    "LOAN_OFFICER", "CREDIT_ANALYST"}:
                continue
            person = user.get("person")
            if person is None:
                person = {}
            first, last = person.get("first_name"), person.get("last_name")
            if any(value is not None and not isinstance(value, str) for value in (first, last)):
                return fail("STAFF_DIRECTORY_UNAVAILABLE", 503)
            name = ((first or "") + " " + (last or "")).strip()[:200] or None
            employees.append({"employee_id": str(identifier), "name": name, "role": role})
        employees.sort(key=lambda item: item["employee_id"])
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        return fail("STAFF_DIRECTORY_UNAVAILABLE", 503)
    return JSONResponse({"employees": employees}, headers=NO_STORE)


# Internal relay endpoints use a dedicated company-bound credential, not staff
# cookies or the LoanHub directory credential. The inbox derives recipients
# and event content independently from persistent records.
class RelayMonitorEvent(BaseModel):
    company_id: UUID
    alert_id: int = Field(strict=True, gt=0, lt=2**63)
    employee_id: UUID
    branch_id: UUID
    event_type: Literal["reported_outside_perimeter", "reported_inside_perimeter"]
    observed_at: datetime
    model_config = {"extra": "forbid"}


class RelayAccessEvent(BaseModel):
    company_id: UUID
    event_id: UUID
    employee_id: UUID
    branch_id: UUID | None
    event_type: Literal["reported_login_outside", "staff_logged_out"]
    observed_at: datetime
    model_config = {"extra": "forbid"}


class RelayMorningEvent(BaseModel):
    company_id: UUID
    employee_id: UUID
    work_date: date
    expires_at: datetime
    model_config = {"extra": "forbid"}


def _relay_context(request, company_id):
    state = request.app.state
    inbox = getattr(state, "staff_attendance_notification_inbox", None)
    token = getattr(state, "staff_attendance_receiver_token", None)
    scope = getattr(state, "staff_attendance_receiver_company_id", None)
    if (getattr(state, "staff_attendance_enabled", False) is not True
            or getattr(state, "staff_attendance_receiver_enabled", False) is not True
            or not isinstance(inbox, AttendanceNotificationInbox)
            or not isinstance(scope, UUID) or inbox._company != scope
            or not isinstance(token, str) or not 32 <= len(token) <= 4096
            or any(not 33 <= ord(c) <= 126 for c in token)):
        return None, fail("ATTENDANCE_RECEIVER_DISABLED", 503)
    authorization = request.headers.get("authorization", "")
    if (not authorization.isascii() or len(authorization) > 4103
            or not secrets.compare_digest(authorization, "Bearer " + token)):
        return None, fail("SERVICE_AUTHENTICATION_REQUIRED", 401)
    if scope != company_id:
        return None, fail("COMPANY_SCOPE_DENIED", 403)
    return inbox, None


def _relay_receipt(company_id, key, outcome, employee_id=None):
    result = {"company_id": str(company_id), "idempotency_key": key,
              "status": outcome.value}
    if employee_id is not None:
        result["employee_id"] = str(employee_id)
    return JSONResponse(result, status_code=200, headers=NO_STORE)


def _receive_owner(payload, request, *, access):
    inbox, denial = _relay_context(request, payload.company_id)
    if denial is not None:
        return denial
    if payload.observed_at.utcoffset() is None:
        return fail("INVALID_EVENT_TIME", 422)
    key = request.headers.get("idempotency-key", "")
    event_id = payload.event_id if access else payload.alert_id
    # Employee, branch, event kind and observed time in the request are not
    # authoritative; the inbox retrieves event content from its source tables.
    try:
        outcome = inbox.accept_owner_event(event_id=event_id, access=access, key=key)
    except (psycopg.Error, ValueError, TypeError):
        return fail("ATTENDANCE_RECEIVER_UNAVAILABLE", 503)
    return _relay_receipt(payload.company_id, key, outcome)


@router.post("/api/v1/attendance/notifications", include_in_schema=False)
def receive_monitor_notification(payload: RelayMonitorEvent, request: Request):
    return _receive_owner(payload, request, access=False)


@router.post("/api/v1/attendance/access-notifications", include_in_schema=False)
def receive_access_notification(payload: RelayAccessEvent, request: Request):
    return _receive_owner(payload, request, access=True)


@router.post("/api/v1/attendance/morning-reminders", include_in_schema=False)
def receive_morning_notification(payload: RelayMorningEvent, request: Request):
    inbox, denial = _relay_context(request, payload.company_id)
    if denial is not None:
        return denial
    expected = datetime.combine(payload.work_date, time(7, 15), tzinfo=LESOTHO)
    if payload.expires_at.utcoffset() is None or payload.expires_at != expected:
        return fail("INVALID_REMINDER_EXPIRY", 422)
    key = request.headers.get("idempotency-key", "")
    try:
        outcome = inbox.accept_morning(employee_id=payload.employee_id,
                                       work_date=payload.work_date, key=key)
    except (psycopg.Error, ValueError, TypeError):
        return fail("ATTENDANCE_RECEIVER_UNAVAILABLE", 503)
    return _relay_receipt(payload.company_id, key, outcome, payload.employee_id)


@router.get("/api/v1/staff/attendance/notifications", include_in_schema=False)
def staff_notifications(request: Request,
                        limit: int = Query(50, ge=1, le=100),
                        before_at: datetime | None = Query(None),
                        before_key: str | None = Query(None, min_length=1, max_length=200)):
    state = request.app.state
    cfg = _config(request)
    inbox = getattr(state, "staff_attendance_notification_inbox", None)
    if (cfg is None or getattr(state, "staff_attendance_enabled", False) is not True
            or getattr(state, "staff_attendance_inbox_enabled", False) is not True
            or not isinstance(inbox, AttendanceNotificationInbox)):
        return fail("ATTENDANCE_INBOX_DISABLED", 503)
    if not safe_staff_read_origin(request, cfg.public_origin):
        return fail("FORBIDDEN_ORIGIN", 403)
    record = cfg.store.resolve(request.cookies.get(COOKIE, ""))
    if record is None:
        return fail("UNAUTHENTICATED", 401)
    if ((before_at is None) != (before_key is None)
            or (before_at is not None and before_at.utcoffset() is None)):
        return fail("INVALID_INBOX_CURSOR", 422)
    try:
        base = cfg.verifier
        staff = LoanHubStaffVerifier(
            origin=cfg.loanhub_origin, public_key=base._public_key,
            batlokoa_company_id=base._company_id, client=base._client,
            allow_unverified_company_owner=False,
        ).verify(record.access_token)
        result = inbox.read_notifications(staff, limit=limit,
                    before_at=before_at, before_key=before_key)
    except (StaffVerificationUnavailable, StaffAccessDenied):
        return fail("STAFF_VERIFICATION_REQUIRED", 403)
    except (psycopg.Error, ValueError):
        return fail("ATTENDANCE_INBOX_UNAVAILABLE", 503)
    return JSONResponse(result, headers=NO_STORE)
