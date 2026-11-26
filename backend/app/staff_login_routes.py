"""Opt-in, single-worker staging employee login using real LoanHub credentials.

NOT a production distributed session store. No access token is sent to the
browser. No customer endpoints, loan writes or MFA bypass are enabled.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import psycopg

import httpx
import jwt
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .loanhub_staff_verifier import LoanHubStaffVerifier, StaffVerificationUnavailable

from .staff_attendance_access_store import AttendanceAccessStore
from .staff_authorization import StaffAccessDenied
from .staff_branch_location import ActiveBranch
from .staff_geofence import Position, LocationState

router = APIRouter()
COOKIE = "__Host-batlokoa_staff_session"
CSRF_COOKIE = "__Host-batlokoa_staff_csrf"
NO_STORE = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


class LoginLocation(BaseModel):
    branch_id: UUID | None = None
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False, strict=True)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False, strict=True)
    accuracy_m: float = Field(gt=0, allow_inf_nan=False, strict=True)
    captured_at: datetime
    model_config = {"extra": "forbid"}


class EmployeeLogin(BaseModel):
    location: LoginLocation | None = None
    phone: str = Field(min_length=8, max_length=30)
    password: str = Field(min_length=6, max_length=128)
    otp: str | None = Field(default=None, min_length=6, max_length=8, pattern=r"^[0-9]{6,8}$")
    recovery_code: str | None = Field(default=None, min_length=8, max_length=32)


@dataclass
class _Record:
    access_token: str
    csrf_token: str
    expires_at: datetime


class StagingStaffSessionStore:
    """Bounded volatile store; restarting the worker logs everyone out.

    Single-process staging only. Production needs shared durable encrypted
    credential storage, distributed revocation and audited key rotation.
    """

    def __init__(self, max_sessions: int = 100):
        if not 1 <= max_sessions <= 1000:
            raise ValueError("Invalid staging session capacity")
        self._items: dict[str, _Record] = {}
        self._limit = max_sessions
        self._lock = Lock()

    def issue(self, token: str, ttl_seconds: int) -> tuple[str, str]:
        session = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        with self._lock:
            now = datetime.now(timezone.utc)
            self._items = {k: v for k, v in self._items.items()
                           if v.expires_at > now}
            if len(self._items) >= self._limit:
                raise StaffVerificationUnavailable("Staging session capacity reached")
            self._items[hashlib.sha256(session.encode()).hexdigest()] = _Record(
                token, csrf, expires
            )
        return session, csrf

    def resolve(self, session: str) -> _Record | None:
        if not isinstance(session, str) or not 32 <= len(session) <= 256:
            return None
        with self._lock:
            key = hashlib.sha256(session.encode()).hexdigest()
            record = self._items.get(key)
            if record and record.expires_at > datetime.now(timezone.utc):
                return record
            self._items.pop(key, None)
        return None

    def revoke(self, session: str) -> None:
        if not isinstance(session, str):
            return
        with self._lock:
            self._items.pop(hashlib.sha256(session.encode()).hexdigest(), None)


@dataclass
class StaffLoginConfig:
    public_origin: str
    loanhub_origin: str
    verifier: LoanHubStaffVerifier
    store: StagingStaffSessionStore
    client: httpx.Client | None = None

    def __post_init__(self):
        for origin in (self.public_origin, self.loanhub_origin):
            p = urlsplit(origin)
            if (p.scheme != "https" or not p.hostname or p.username
                    or p.password or p.path not in ("", "/")
                    or p.query or p.fragment):
                raise ValueError("Trusted HTTPS origin required")
        if not isinstance(self.verifier, LoanHubStaffVerifier):
            raise ValueError("Trusted staff verifier required")
        if not isinstance(self.store, StagingStaffSessionStore):
            raise ValueError("Staging store required")
        if self.loanhub_origin.rstrip("/") != self.verifier._origin:
            raise ValueError("LoanHub origin does not match staff verifier")


def _config(request: Request) -> StaffLoginConfig | None:
    cfg = getattr(request.app.state, "staff_login_config", None)
    return cfg if isinstance(cfg, StaffLoginConfig) else None


def _response(code: str, status: int) -> JSONResponse:
    return JSONResponse({"code": code}, status_code=status, headers=NO_STORE)


def _same_origin(request: Request, origin: str) -> bool:
    return request.headers.get("origin") == origin.rstrip("/")


def _login_location(request, cfg, token, location):
    """Observe only after successful authentication; never claim missing GPS is outside."""
    store = getattr(request.app.state, "staff_attendance_access_store", None)
    if (getattr(request.app.state, "staff_attendance_enabled", False) is not True
            or getattr(request.app.state, "staff_login_location_enabled", False) is not True):
        return None
    if not isinstance(store, AttendanceAccessStore) or location is None:
        return LocationState.UNVERIFIED.value
    try:
        base = cfg.verifier
        identity = LoanHubStaffVerifier(
            origin=cfg.loanhub_origin, public_key=base._public_key,
            batlokoa_company_id=base._company_id, client=base._client,
            allow_unverified_company_owner=False,
        ).verify(token)
        # The verified membership is authoritative, never a browser-selected
        # office. Accounts without exactly one assigned branch are ambiguous.
        if len(identity.branch_ids) != 1:
            return LocationState.UNVERIFIED.value
        branch_id = next(iter(identity.branch_ids))
        if location.branch_id is not None and location.branch_id != branch_id:
            return LocationState.UNVERIFIED.value
        def read(client):
            return client.get(cfg.loanhub_origin.rstrip("/") + "/api/v1/branches/?limit=100",
                headers={"Authorization": "Bearer " + token,
                         "X-Company-ID": str(identity.company_id),
                         "X-Active-Role": identity.role.lower(),
                         "Accept": "application/json", "Cache-Control": "no-store"},
                timeout=8, follow_redirects=False)
        if cfg.client is None:
            with httpx.Client(trust_env=False, follow_redirects=False) as client:
                response = read(client)
        else:
            response = read(cfg.client)
        if (response.status_code != 200 or len(response.content) > 131072
                or "application/json" not in response.headers.get("content-type", "").lower()):
            return LocationState.UNVERIFIED.value
        rows = response.json()
        if not isinstance(rows, list) or len(rows) > 100:
            return LocationState.UNVERIFIED.value
        seen, active = set(), set()
        for row in rows:
            if UUID(str(row["company_id"])) != identity.company_id:
                return LocationState.UNVERIFIED.value
            identifier = UUID(str(row["id"]))
            if identifier in seen:
                return LocationState.UNVERIFIED.value
            seen.add(identifier)
            if row.get("is_active") is True:
                active.add(identifier)
        if branch_id not in active:
            return LocationState.UNVERIFIED.value
        reading, _ = store.record_login(identity, uuid4(),
            ActiveBranch(identity.company_id, branch_id, True),
            Position(location.latitude, location.longitude, location.accuracy_m),
            captured_at=location.captured_at)
        return reading.value
    except (StaffVerificationUnavailable, StaffAccessDenied, psycopg.Error,
            httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        return LocationState.UNVERIFIED.value


@router.post("/api/v1/staff/login", include_in_schema=False)
def staff_login(payload: EmployeeLogin, request: Request):
    cfg = _config(request)
    if cfg is None:
        return _response("STAFF_LOGIN_DISABLED", 503)
    if not _same_origin(request, cfg.public_origin):
        return _response("FORBIDDEN_ORIGIN", 403)
    if payload.otp is not None and payload.recovery_code is not None:
        return _response("LOGIN_FAILED", 401)
    try:
        def call(client: httpx.Client):
            return client.post(
                cfg.loanhub_origin.rstrip("/") + "/api/v1/auth/login",
                json={"phone": payload.phone.strip(), "password": payload.password,
                      **({"otp": payload.otp} if payload.otp else {}),
                      **({"recovery_code": payload.recovery_code} if payload.recovery_code else {})},
                headers={"Accept": "application/json", "Cache-Control": "no-store"},
                timeout=5, follow_redirects=False,
            )
        if cfg.client is None:
            with httpx.Client(trust_env=False, follow_redirects=False) as client:
                upstream = call(client)
        else:
            upstream = call(cfg.client)
        if (upstream.status_code != 200 or len(upstream.content) > 16384
                or "application/json" not in
                upstream.headers.get("content-type", "").lower()):
            return _response("LOGIN_FAILED", 401)
        result = upstream.json()
        if not isinstance(result, dict) or result.get("token_type") != "bearer":
            return _response("LOGIN_FAILED", 401)
        token = result.get("access_token")
        if not isinstance(token, str):
            return _response("LOGIN_FAILED", 401)
        identity = cfg.verifier.verify(token)
        # Only after verifier's RS256 verification is reading expiry safe.
        exp = jwt.decode(token, options={"verify_signature": False})["exp"]
        remaining = int(exp - datetime.now(timezone.utc).timestamp())
        if remaining <= 0:
            return _response("LOGIN_FAILED", 401)
        ttl = min(remaining, 600)
        location_state = _login_location(request, cfg, token, payload.location)
        remaining = int(exp - datetime.now(timezone.utc).timestamp())
        if remaining <= 0:
            return _response("LOGIN_FAILED", 401)
        ttl = min(remaining, 600)
        session, csrf = cfg.store.issue(token, ttl)
        response = JSONResponse({
            **({"login_location": location_state} if location_state is not None else {}),
            "authenticated": True,
            "role": identity.role,
            "company_id": str(identity.company_id),
            "branch_ids": sorted(map(str, identity.branch_ids)),
            "company_wide_scope": identity.company_wide_scope,
        }, headers=NO_STORE)
        response.set_cookie(COOKIE, session, secure=True, httponly=True,
                            samesite="strict", path="/", max_age=ttl)
        response.set_cookie(CSRF_COOKIE, csrf, secure=True, httponly=False,
                            samesite="strict", path="/", max_age=ttl)
        return response
    except (StaffVerificationUnavailable, httpx.HTTPError, jwt.PyJWTError,
            ValueError, TypeError, KeyError, OverflowError):
        return _response("LOGIN_FAILED", 401)


@router.get("/api/v1/staff/session", include_in_schema=False)
def staff_session(request: Request):
    cfg = _config(request)
    if cfg is None:
        return _response("STAFF_LOGIN_DISABLED", 503)
    session = request.cookies.get(COOKIE, "")
    record = cfg.store.resolve(session)
    if record is None:
        return _response("UNAUTHENTICATED", 401)
    try:
        identity = cfg.verifier.verify(record.access_token)
    except StaffVerificationUnavailable:
        cfg.store.revoke(session)
        return _response("UNAUTHENTICATED", 401)
    return JSONResponse({
        "authenticated": True,
        "role": identity.role,
        "company_id": str(identity.company_id),
        "branch_ids": sorted(map(str, identity.branch_ids)),
        "company_wide_scope": identity.company_wide_scope,
    }, headers=NO_STORE)


@router.post("/api/v1/staff/logout", include_in_schema=False)
def staff_logout(request: Request):
    cfg = _config(request)
    if cfg is None:
        return _response("STAFF_LOGIN_DISABLED", 503)
    if not _same_origin(request, cfg.public_origin):
        return _response("FORBIDDEN_ORIGIN", 403)
    session = request.cookies.get(COOKIE, "")
    record = cfg.store.resolve(session)
    csrf = request.headers.get("x-csrf-token", "")
    if (record is None or not csrf or
            not secrets.compare_digest(csrf, record.csrf_token) or
            request.cookies.get(CSRF_COOKIE) != csrf):
        return _response("CSRF_REJECTED", 403)
    cfg.store.revoke(session)
    response = JSONResponse({"logged_out": True}, headers=NO_STORE)
    response.delete_cookie(COOKIE, secure=True, httponly=True,
                           samesite="strict", path="/")
    response.delete_cookie(CSRF_COOKIE, secure=True, httponly=False,
                           samesite="strict", path="/")
    return response
