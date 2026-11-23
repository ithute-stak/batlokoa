"""Staged Batlokoa-to-LoanHub new-client transport; not wired to a live route.

A server-side release gate must be independently authorized after the identity
migration, security review and an authenticated integration test. Browser flags
and upstream informational responses cannot authorize writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, StrictBool

from .staff_authorization import (
    VerifiedStaffIdentity, StaffPermission, require_staff_permission,
)


class ClientCreationNotReleased(RuntimeError):
    pass


class ClientCreationUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class CreatedClient:
    account_id: UUID
    replayed: bool


class NewClientReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_account_id: UUID
    replayed: StrictBool


def post_new_only_client(
    *,
    staff: VerifiedStaffIdentity,
    branch_id: UUID,
    loanhub_origin: str,
    loanhub_access_token: str,
    complete_payload: dict,
    idempotency_key: str,
    client: httpx.Client,
    independently_approved_release: bool = False,
) -> CreatedClient:
    """Internal-only transport to a reviewed LoanHub new-only API.

    No route invokes this in the current application. Keep the default false
    until LoanHub has *actually* activated the protected new-only POST route.
    Never call the legacy /company-clients assisted writer.
    """
    if independently_approved_release is not True:
        raise ClientCreationNotReleased("New-client creation is not released")
    if not isinstance(staff, VerifiedStaffIdentity):
        raise ClientCreationUnavailable("Verified LoanHub staff is required")
    require_staff_permission(
        staff, expected_company_id=staff.company_id,
        branch_id=branch_id, permission=StaffPermission.REGISTER_CLIENT,
    )
    if (
        not isinstance(complete_payload, dict)
        or complete_payload.get("branch_id") != str(branch_id)
        or any(k in complete_payload for k in (
            "company_id", "user_id", "employee_id", "role",
            "independently_approved_release",
        ))
    ):
        raise ClientCreationUnavailable("Untrusted client creation scope")
    if (
        not isinstance(idempotency_key, str)
        or not 16 <= len(idempotency_key) <= 128
        or any(not (ch.isascii() and (ch.isalnum() or ch in "-_.")) for ch in idempotency_key)
    ):
        raise ClientCreationUnavailable("Valid idempotency key required")
    if not isinstance(loanhub_access_token, str) or not loanhub_access_token:
        raise ClientCreationUnavailable("Authenticated upstream token required")
    if (
        not isinstance(loanhub_origin, str)
        or not loanhub_origin.isascii()
        or any(ord(char) <= 32 or ord(char) == 127 for char in loanhub_origin)
    ):
        raise ClientCreationUnavailable("Trusted HTTPS LoanHub origin required")
    try:
        parsed_origin = urlsplit(loanhub_origin)
        # Port is optional. Reading .port also rejects malformed port values.
        port = parsed_origin.port
        valid_origin = (
            parsed_origin.scheme == "https"
            and bool(parsed_origin.hostname)
            and parsed_origin.username is None
            and parsed_origin.password is None
            and parsed_origin.path in ("", "/")
            and not parsed_origin.query
            and not parsed_origin.fragment
            and parsed_origin.netloc
            == (parsed_origin.hostname if port is None
                else f"{parsed_origin.hostname}:{port}")
        )
    except ValueError:
        valid_origin = False
    if not valid_origin:
        raise ClientCreationUnavailable("Trusted HTTPS LoanHub origin required")

    try:
        response = client.post(
            loanhub_origin.rstrip("/") + "/api/v1/batlokoa/registration/clients",
            json=complete_payload,
            headers={
                "Authorization": "Bearer " + loanhub_access_token,
                "X-Company-ID": str(staff.company_id),
                "Idempotency-Key": idempotency_key,
                "Accept": "application/json",
                "Cache-Control": "no-store",
            },
            timeout=10.0,
            follow_redirects=False,
        )
        if (
            response.status_code not in (200, 201)
            or len(response.content) > 4096
            or "application/json" not in response.headers.get("content-type", "").lower()
        ):
            raise ClientCreationUnavailable("LoanHub registration not confirmed")
        receipt = NewClientReceipt.model_validate(response.json())
        return CreatedClient(receipt.client_account_id, receipt.replayed)
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        raise ClientCreationUnavailable("LoanHub registration not confirmed") from exc
