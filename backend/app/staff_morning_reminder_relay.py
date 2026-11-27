"""Candidate morning notification relay; requires a separately certified receiver."""
from datetime import date, datetime, time, timezone
from urllib.parse import urlsplit
from uuid import UUID
import json

import httpx

from .staff_morning_reminder import LESOTHO
from .staff_morning_reminder_queue import MorningReminderClaim
from .staff_attendance_dispatch_worker import DispatchOutcome


class MorningReminderRelayProvider:
    def __init__(self, *, origin, company_id, token, client=None, clock=None):
        parsed = urlsplit(origin)
        if (parsed.scheme != "https" or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
            raise ValueError("Pinned HTTPS relay origin required")
        if not isinstance(company_id, UUID):
            raise ValueError("Explicit company scope required")
        if (not isinstance(token, str) or not 32 <= len(token) <= 4096
                or any(not 33 <= ord(c) <= 126 for c in token)):
            raise ValueError("Invalid relay credential")
        self._url = origin.rstrip("/") + "/api/v1/attendance/morning-reminders"
        self._company = company_id
        self._token = token
        self._client = client
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def send(self, claim, *, idempotency_key):
        if (not isinstance(claim, MorningReminderClaim)
                or claim.company_id != self._company
                or not isinstance(claim.employee_id, UUID)
                or type(claim.work_date) is not date
                or idempotency_key != claim.idempotency_key):
            return DispatchOutcome.REJECTED
        now = self._clock()
        if not isinstance(now, datetime) or now.utcoffset() is None:
            return DispatchOutcome.RETRY
        local = now.astimezone(LESOTHO)
        if local.date() != claim.work_date or not time(7) <= local.time() < time(7, 15):
            return DispatchOutcome.REJECTED
        expiry = datetime.combine(claim.work_date, time(7, 15), tzinfo=LESOTHO)
        payload = {"company_id": str(self._company),
                   "employee_id": str(claim.employee_id),
                   "work_date": claim.work_date.isoformat(),
                   "expires_at": expiry.isoformat()}

        def post(client):
            with client.stream("POST", self._url, json=payload,
                    headers={"Authorization": "Bearer " + self._token,
                             "Idempotency-Key": idempotency_key,
                             "Accept": "application/json", "Cache-Control": "no-store"},
                    follow_redirects=False, timeout=10) as response:
                if (response.status_code not in (200, 202)
                        or "application/json" not in response.headers.get("content-type", "").lower()):
                    return DispatchOutcome.RETRY
                body = bytearray()
                for chunk in response.iter_bytes(chunk_size=1024):
                    body.extend(chunk)
                    if len(body) > 4096:
                        return DispatchOutcome.RETRY
                receipt = json.loads(body)
                if (not isinstance(receipt, dict)
                        or receipt.get("company_id") != str(self._company)
                        or receipt.get("employee_id") != str(claim.employee_id)
                        or receipt.get("idempotency_key") != idempotency_key):
                    return DispatchOutcome.RETRY
                status = receipt.get("status")
                if status == "accepted":
                    return DispatchOutcome.ACCEPTED
                if status == "rejected":
                    return DispatchOutcome.REJECTED
                if status == "recipient_unavailable":
                    return DispatchOutcome.RECIPIENT_UNAVAILABLE
                return DispatchOutcome.RETRY
        try:
            if self._client is not None:
                return post(self._client)
            with httpx.Client(trust_env=False, follow_redirects=False) as client:
                return post(client)
        except (httpx.HTTPError, ValueError, TypeError):
            return DispatchOutcome.RETRY
