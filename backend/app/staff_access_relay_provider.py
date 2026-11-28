"""Candidate HTTPS access-event notification relay adapter; no live relay is configured.

The trusted relay must authenticate the caller, resolve current authorized
company-owner recipients, and persist idempotency keys atomically with its
send queue. No destination contact details or GPS coordinates are transmitted.
"""
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from .staff_attendance_dispatch_worker import DispatchOutcome
from .staff_access_notification_queue import AccessDeliveryClaim


class AccessRelayProvider:
    def __init__(self, *, origin, company_id, token, client=None):
        parsed = urlsplit(origin)
        if (parsed.scheme != "https" or not parsed.hostname
                or parsed.username or parsed.password or parsed.query
                or parsed.fragment or parsed.path not in ("", "/")):
            raise ValueError("Pinned HTTPS relay origin required")
        if not isinstance(company_id, UUID):
            raise ValueError("Explicit company scope required")
        if (not isinstance(token, str) or not 1 <= len(token) <= 4096
                or any(c.isspace() or not 33 <= ord(c) <= 126 for c in token)):
            raise ValueError("Invalid relay credential")
        self._url = origin.rstrip("/") + "/api/v1/attendance/access-notifications"
        self._company_id = company_id
        self._token = token
        self._client = client

    def send(self, claim, *, idempotency_key):
        if (not isinstance(claim, AccessDeliveryClaim)
                or claim.company_id != self._company_id
                or idempotency_key != claim.idempotency_key
                or claim.event_type not in {
                    "reported_login_outside", "staff_logged_out"
                }
                or not isinstance(claim.event_id, UUID)
                or not isinstance(claim.employee_id, UUID)
                or (claim.branch_id is not None and not isinstance(claim.branch_id, UUID))
                or (claim.event_type == "reported_login_outside" and claim.branch_id is None)
                or claim.observed_at.utcoffset() is None):
            return DispatchOutcome.REJECTED
        payload = {
            "company_id": str(claim.company_id),
            "event_id": str(claim.event_id),
            "employee_id": str(claim.employee_id),
            "branch_id": str(claim.branch_id) if claim.branch_id is not None else None,
            "event_type": claim.event_type,
            "observed_at": claim.observed_at.isoformat(),
        }

        def post(client):
            with client.stream("POST", self._url,
                    headers={"Authorization": "Bearer " + self._token,
                             "Idempotency-Key": idempotency_key,
                             "Accept": "application/json",
                             "Cache-Control": "no-store"},
                    json=payload, follow_redirects=False, timeout=10) as response:
                if response.status_code not in (200, 202):
                    return DispatchOutcome.RETRY
                if "application/json" not in response.headers.get("content-type", "").lower():
                    return DispatchOutcome.RETRY
                body = bytearray()
                for chunk in response.iter_bytes(chunk_size=1024):
                    body.extend(chunk)
                    if len(body) > 4096:
                        return DispatchOutcome.RETRY
                import json
                receipt = json.loads(body)
                if (not isinstance(receipt, dict)
                        or receipt.get("idempotency_key") != idempotency_key
                        or receipt.get("company_id") != str(self._company_id)):
                    return DispatchOutcome.RETRY
                status = receipt.get("status")
                if status == "accepted":
                    return DispatchOutcome.ACCEPTED
                if status == "recipient_unavailable":
                    return DispatchOutcome.RECIPIENT_UNAVAILABLE
                if status == "rejected":
                    return DispatchOutcome.REJECTED
                return DispatchOutcome.RETRY

        try:
            if self._client is not None:
                return post(self._client)
            with httpx.Client(trust_env=False, follow_redirects=False) as client:
                return post(client)
        except (httpx.HTTPError, ValueError, TypeError):
            return DispatchOutcome.RETRY
