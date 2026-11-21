"""Opt-in read-only staff client directory through verified LoanHub identity.

Uses the server-held staging session token, never a browser-supplied bearer,
role or company. LoanHub independently enforces tenant/branch authorization.
No registration, loan or financial mutation route is enabled here.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from .loanhub_staff_clients import (
    LoanHubStaffClientDirectory,
    StaffDirectoryUnavailable,
)
from .loanhub_staff_verifier import StaffVerificationUnavailable
from .staff_authorization import StaffAccessDenied
from .staff_login_routes import COOKIE, NO_STORE, _config

router = APIRouter()


def _error(code: str, status: int) -> JSONResponse:
    return JSONResponse({"code": code}, status_code=status, headers=NO_STORE)


@router.get("/api/v1/staff/clients", include_in_schema=False)
def staff_clients(
    request: Request,
    search: str = Query(default="", max_length=120),
    limit: int = Query(default=30, ge=1, le=100),
    branch_id: UUID | None = None,
):
    """Read minimum client directory fields; never expose borrower identifiers."""
    cfg = _config(request)
    directory = getattr(request.app.state, "staff_client_directory", None)
    # Both switches must be provided explicitly by a trusted staging
    # bootstrap. The production/demo defaults remain disabled.
    if (
        cfg is None
        or getattr(request.app.state, "staff_client_directory_enabled", False) is not True
        or not isinstance(directory, LoanHubStaffClientDirectory)
        or directory._origin != cfg.loanhub_origin.rstrip("/")
    ):
        return _error("STAFF_CLIENT_DIRECTORY_DISABLED", 503)

    cookie = request.cookies.get(COOKIE, "")
    record = cfg.store.resolve(cookie)
    if record is None:
        return _error("UNAUTHENTICATED", 401)

    try:
        verified = cfg.verifier.verify(record.access_token)
        results = directory.search(
            verified_staff=verified,
            staff_access_token=record.access_token,
            search=search,
            branch_id=branch_id,
            limit=limit,
        )
        return JSONResponse(
            {"clients": [
                {
                    "account_id": str(client.account_id),
                    "account_reference": client.account_reference,
                    "company_id": str(client.company_id),
                    "branch_id": str(client.branch_id) if client.branch_id else None,
                    "full_name": client.full_name,
                    "status": client.status,
                }
                for client in results
            ]},
            headers=NO_STORE,
        )
    except StaffVerificationUnavailable:
        cfg.store.revoke(cookie)
        return _error("UNAUTHENTICATED", 401)
    except StaffAccessDenied:
        return _error("FORBIDDEN_STAFF_SCOPE", 403)
    except (StaffDirectoryUnavailable, ValueError, TypeError, KeyError):
        return _error("CLIENT_DIRECTORY_UNAVAILABLE", 503)
