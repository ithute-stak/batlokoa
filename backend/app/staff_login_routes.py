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

import httpx
import jwt
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .loanhub_staff_verifier import LoanHubStaffVerifier, StaffVerificationUnavailable

router = APIRouter()
COOKIE = "__Host-batlokoa_staff_session"
CSRF_COOKIE = "__Host-batlokoa_staff_csrf"
NO_STORE = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


class EmployeeLogin(BaseModel):
    phone: str = Field(min_length=8, max_length=30)
    password: str = Field(min_length=6, max_length=128)


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


@router.post("/api/v1/staff/login", include_in_schema=False)
def staff_login(payload: EmployeeLogin, request: Request):
    cfg = _config(request)
    if cfg is None:
        return _response("STAFF_LOGIN_DISABLED", 503)
    if not _same_origin(request, cfg.public_origin):
        return _response("FORBIDDEN_ORIGIN", 403)
    try:
        def call(client: httpx.Client):
            return client.post(
                cfg.loanhub_origin.rstrip("/") + "/api/v1/auth/login",
                json={"phone": payload.phone.strip(), "password": payload.password},
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
        session, csrf = cfg.store.issue(token, ttl)
        response = JSONResponse({
            "authenticated": True,
            "role": identity.role,
            "company_id": str(identity.company_id),
            "branch_ids": sorted(map(str, identity.branch_ids)),
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
