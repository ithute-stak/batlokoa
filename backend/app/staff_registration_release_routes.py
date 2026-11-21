"""Employee-facing registration release status; no client write route."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .loanhub_registration_release_status import (
    LoanHubRegistrationReleaseStatus, RegistrationReleaseStatusUnavailable,
)
from .loanhub_staff_verifier import StaffVerificationUnavailable
from .staff_authorization import StaffAccessDenied
from .staff_login_routes import COOKIE, NO_STORE, _config

router = APIRouter()


def _error(code: str, status: int) -> JSONResponse:
    return JSONResponse({"code": code}, status_code=status, headers=NO_STORE)


@router.get("/api/v1/staff/clients/registration-release-status", include_in_schema=False)
def registration_release_status(request: Request):
    cfg = _config(request)
    adapter = getattr(request.app.state, "staff_registration_release_adapter", None)
    if (
        cfg is None
        or getattr(
            request.app.state, "staff_registration_release_status_enabled", False
        ) is not True
        or not isinstance(adapter, LoanHubRegistrationReleaseStatus)
        or adapter._origin != cfg.loanhub_origin.rstrip("/")
    ):
        return _error("REGISTRATION_RELEASE_STATUS_DISABLED", 503)
    session = request.cookies.get(COOKIE, "")
    record = cfg.store.resolve(session)
    if record is None:
        return _error("UNAUTHENTICATED", 401)

    try:
        staff = cfg.verifier.verify(record.access_token)
        status = adapter.inspect(staff=staff, access_token=record.access_token)
    except StaffVerificationUnavailable:
        cfg.store.revoke(session)
        return _error("UNAUTHENTICATED", 401)
    except StaffAccessDenied:
        return _error("FORBIDDEN_STAFF_SCOPE", 403)
    except (RegistrationReleaseStatusUnavailable, ValueError, TypeError):
        return _error("REGISTRATION_RELEASE_STATUS_UNAVAILABLE", 503)

    return JSONResponse({
        "state": status.state,
        "can_submit": False,
        "requires_identity_migration_approval": True,
        "requires_independent_release_approval": True,
        "client_creation_enabled": False,
    }, headers=NO_STORE)
