"""Opt-in branch geofence registration; browser coordinates are not attestation."""
import secrets
from datetime import datetime, timezone
from uuid import UUID

import httpx
import psycopg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .owner_staff_management_routes import owner_context, call_loanhub, fail
from .staff_login_routes import CSRF_COOKIE, NO_STORE, _config, _same_origin
from .staff_branch_location import ActiveBranch
from .staff_branch_location_store import BranchLocationStore
from .staff_geofence import Position
from .staff_authorization import StaffAccessDenied

router = APIRouter()


class LocationCapture(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False, strict=True)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False, strict=True)
    accuracy_m: float = Field(gt=0, le=5, allow_inf_nan=False, strict=True)
    captured_at: datetime
    confirm: bool = Field(strict=True)
    model_config = {"extra": "forbid"}


@router.post("/api/v1/staff/manage/branches/{branch_id}/location", include_in_schema=False)
def register_location(branch_id: UUID, payload: LocationCapture, request: Request):
    store = getattr(request.app.state, "staff_branch_location_store", None)
    if (getattr(request.app.state, "staff_branch_location_enabled", False) is not True
            or not isinstance(store, BranchLocationStore)):
        return fail("BRANCH_LOCATION_DISABLED", 503)
    cfg = _config(request)
    if cfg is None:
        return fail("BRANCH_LOCATION_DISABLED", 503)
    if not _same_origin(request, cfg.public_origin):
        return fail("FORBIDDEN_ORIGIN", 403)
    record, staff, denial = owner_context(request, require_verified=True)
    if denial is not None:
        return denial
    csrf = request.headers.get("x-csrf-token", "")
    if (not csrf or not csrf.isascii()
            or request.cookies.get(CSRF_COOKIE) != csrf
            or not secrets.compare_digest(csrf, record.csrf_token)):
        return fail("CSRF_REJECTED", 403)
    if not payload.confirm or payload.captured_at.utcoffset() is None:
        return fail("LOCATION_CONFIRMATION_REQUIRED", 422)
    try:
        response = call_loanhub(
            request, method="GET", path="/api/v1/branches/?limit=100",
            token=record.access_token, company_id=staff.company_id,
        )
        if (response.status_code != 200 or len(response.content) > 131072
                or "application/json" not in response.headers.get("content-type", "").lower()):
            return fail("BRANCH_DIRECTORY_UNAVAILABLE", 503)
        data = response.json()
        if not isinstance(data, list) or len(data) > 100:
            return fail("BRANCH_DIRECTORY_UNAVAILABLE", 503)
        seen = set()
        active = set()
        for item in data:
            if UUID(str(item["company_id"])) != staff.company_id:
                return fail("BRANCH_DIRECTORY_UNAVAILABLE", 503)
            identifier = UUID(str(item["id"]))
            if identifier in seen:
                return fail("BRANCH_DIRECTORY_UNAVAILABLE", 503)
            seen.add(identifier)
            if item.get("is_active") is True:
                active.add(identifier)
        if branch_id not in active:
            return fail("BRANCH_NOT_AUTHORIZED", 403)
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        return fail("BRANCH_DIRECTORY_UNAVAILABLE", 503)
    # Client timestamp is only a plausibility check, not trusted GPS evidence.
    age = (datetime.now(timezone.utc) - payload.captured_at).total_seconds()
    if not -5 <= age <= 30:
        return fail("LOCATION_CAPTURE_EXPIRED", 422)
    try:
        revision, timestamp = store.register(
            staff, ActiveBranch(staff.company_id, branch_id, True),
            Position(payload.latitude, payload.longitude, payload.accuracy_m),
            fresh=True,
        )
    except StaffAccessDenied:
        return fail("BRANCH_NOT_AUTHORIZED", 403)
    except (ValueError, psycopg.Error):
        return fail("BRANCH_LOCATION_UNAVAILABLE", 503)
    return JSONResponse({
        "registered": True, "revision_id": revision,
        "registered_at": timestamp.isoformat(), "radius_m": 10,
    }, status_code=201, headers=NO_STORE)
