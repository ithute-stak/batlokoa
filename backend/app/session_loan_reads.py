"""Disabled-by-default, cookie-session loan-read boundary.

Only a separately approved bootstrap may configure this route. No bearer
credentials or tenant/customer IDs are accepted from browser requests.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .auth_routes import SESSION_COOKIE
from .loan_reads import LoanReadForbidden, LoanReadService, LoanReadUnavailable
from .loanhub_adapter import LoanHubReadError
from .sessions import PostgresSessionStore


@dataclass(frozen=True)
class SessionLoanReadConfig:
    sessions: PostgresSessionStore
    service: LoanReadService
    public_origin: str

    def __post_init__(self) -> None:
        url = urlsplit(self.public_origin)
        if (url.scheme != "https" or not url.hostname or
                url.path not in ("", "/") or url.query or url.fragment or
                url.username or url.password):
            raise ValueError("Approved HTTPS origin is required")


router = APIRouter()


def _error(status: int, code: str) -> JSONResponse:
    return JSONResponse(
        {"code": code}, status_code=status,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@router.get("/api/v1/me/loans/session", include_in_schema=False)
async def session_customer_loans(request: Request) -> JSONResponse:
    config = getattr(request.app.state, "session_loan_read_config", None)
    if not isinstance(config, SessionLoanReadConfig):
        return _error(503, "INTEGRATION_DISABLED")

    # Require modern browser same-origin fetch metadata. Reject cross-origin
    # and direct requests rather than using their claims as authorization.
    if (request.headers.get("sec-fetch-site") != "same-origin" or
            request.headers.get("origin", config.public_origin) != config.public_origin or
            request.headers.get("authorization")):
        return _error(403, "FORBIDDEN_ORIGIN")

    try:
        active = await config.sessions.resolve(request.cookies.get(SESSION_COOKIE, ""))
    except Exception:
        return _error(503, "SESSION_UNAVAILABLE")
    if active is None:
        return _error(401, "UNAUTHENTICATED")

    try:
        loans = await config.service.list_for_resolved_session(context=active.context)
    except LoanReadForbidden:
        return _error(403, "NOT_AUTHORIZED")
    except (LoanReadUnavailable, LoanHubReadError):
        return _error(503, "LOAN_SERVICE_UNAVAILABLE")
    except Exception:
        # Do not expose upstream exceptions or data in error bodies.
        return _error(503, "LOAN_SERVICE_UNAVAILABLE")
    return JSONResponse(
        {"loans": [row.model_dump(mode="json") for row in loans]},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
