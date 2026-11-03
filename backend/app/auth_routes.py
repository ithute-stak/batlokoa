"""Opt-in BFF authentication endpoints. No provider is configured by default."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .oidc_login import LoginDenied, LoginUnavailable, OidcLoginService
from .sessions import PostgresSessionStore, SessionDenied

router = APIRouter()
STATE_COOKIE = "__Host-batlokoa_login_state"
SESSION_COOKIE = "__Host-batlokoa_session"


@dataclass(frozen=True)
class AuthRouteConfig:
    login: OidcLoginService
    sessions: PostgresSessionStore
    public_origin: str

    def __post_init__(self) -> None:
        parts = urlsplit(self.public_origin)
        if (parts.scheme != "https" or not parts.hostname or parts.path not in ("", "/")
                or parts.query or parts.fragment or parts.username or parts.password):
            raise ValueError("BFF public origin must be a trusted HTTPS origin")
        if not self.login.redirect_uri.startswith(self.public_origin.rstrip("/") + "/"):
            raise ValueError("OIDC callback origin mismatch")


def unavailable() -> JSONResponse:
    return JSONResponse({"code": "AUTH_DISABLED"}, status_code=503,
                        headers={"Cache-Control": "no-store"})


def _config(request: Request) -> AuthRouteConfig | None:
    config = getattr(request.app.state, "auth_route_config", None)
    return config if isinstance(config, AuthRouteConfig) else None


def _same_origin(request: Request, origin: str) -> bool:
    return request.headers.get("origin") == origin.rstrip("/")


@router.get("/api/v1/auth/login", include_in_schema=False)
async def start_login(request: Request):
    config = _config(request)
    if config is None:
        return unavailable()
    try:
        url, state = await config.login.begin()
    except Exception:
        return JSONResponse({"code": "AUTH_UNAVAILABLE"}, status_code=503,
                            headers={"Cache-Control": "no-store"})
    response = RedirectResponse(url, status_code=303,
                                headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
    # Lax is necessary for the cross-site top-level redirect back from the IdP.
    response.set_cookie(STATE_COOKIE, state, secure=True, httponly=True,
                        samesite="lax", max_age=300, path="/")
    return response


@router.get("/api/v1/auth/callback", include_in_schema=False)
async def finish_login(request: Request, code: str = "", state: str = ""):
    config = _config(request)
    if config is None:
        return unavailable()
    cookie_state = request.cookies.get(STATE_COOKIE, "")
    try:
        grant = await config.login.finish(
            state=state, cookie_state=cookie_state, code=code)
    except (LoginDenied, LoginUnavailable, SessionDenied):
        response = JSONResponse({"code": "LOGIN_FAILED"}, status_code=401,
                                headers={"Cache-Control": "no-store"})
    else:
        response = RedirectResponse(config.public_origin.rstrip("/") + "/",
                                    status_code=303,
                                    headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
        max_age = max(0, int((grant.expires_at - __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc)).total_seconds()))
        response.set_cookie(SESSION_COOKIE, grant.session_token, secure=True,
                            httponly=True, samesite="strict", max_age=max_age, path="/")
        # CSRF proof must be returned only to the authenticated same-origin app.
        # It is intentionally NOT placed in the redirect URL or a readable cookie.
        # A later authenticated CSRF bootstrap route is required for writes.
    response.delete_cookie(STATE_COOKIE, secure=True, httponly=True,
                           samesite="lax", path="/")
    return response


@router.get("/api/v1/auth/session", include_in_schema=False)
async def session_status(request: Request):
    config = _config(request)
    if config is None:
        return unavailable()
    token = request.cookies.get(SESSION_COOKIE, "")
    active = await config.sessions.resolve(token)
    return JSONResponse({"authenticated": active is not None},
                        headers={"Cache-Control": "no-store"})


@router.post("/api/v1/auth/logout", include_in_schema=False)
async def logout(request: Request):
    config = _config(request)
    if config is None:
        return unavailable()
    if not _same_origin(request, config.public_origin):
        return JSONResponse({"code": "FORBIDDEN_ORIGIN"}, status_code=403,
                            headers={"Cache-Control": "no-store"})
    token = request.cookies.get(SESSION_COOKIE, "")
    csrf = request.headers.get("x-csrf-token", "")
    active = await config.sessions.resolve(
        token, csrf_token=csrf, require_csrf=True)
    if active is None:
        return JSONResponse({"code": "UNAUTHENTICATED"}, status_code=401,
                            headers={"Cache-Control": "no-store"})
    await config.sessions.revoke(token)
    response = JSONResponse({"logged_out": True},
                            headers={"Cache-Control": "no-store"})
    response.delete_cookie(SESSION_COOKIE, secure=True, httponly=True,
                           samesite="strict", path="/")
    return response
