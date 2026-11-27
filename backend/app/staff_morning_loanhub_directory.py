"""Candidate service-to-service LoanHub roster client.

Requires a dedicated read-only, company-bound credential and a matching
LoanHub endpoint. Never reuse an employee or owner browser session.
"""
import json
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from .staff_authorization import VerifiedStaffIdentity


class LoanHubMorningDirectory:
    def __init__(self, *, origin, company_id, token, client=None):
        parsed = urlsplit(origin)
        if (parsed.scheme != "https" or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
            raise ValueError("Pinned HTTPS origin required")
        if not isinstance(company_id, UUID):
            raise ValueError("Explicit company scope required")
        if (not isinstance(token, str) or not 1 <= len(token) <= 4096
                or any(not 33 <= ord(c) <= 126 for c in token)):
            raise ValueError("Invalid service credential")
        self._url = origin.rstrip("/") + "/api/v1/integrations/attendance/employees"
        self._company = company_id
        self._token = token
        self._client = client

    def employees(self, *, company_id, limit):
        if company_id != self._company or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid directory scope or limit")

        def read(client):
            with client.stream("GET", self._url,
                    params={"company_id": str(self._company), "limit": limit},
                    headers={"Authorization": "Bearer " + self._token,
                             "Accept": "application/json", "Cache-Control": "no-store"},
                    follow_redirects=False, timeout=10) as response:
                if (response.status_code != 200 or
                        "application/json" not in response.headers.get("content-type", "").lower()):
                    raise ValueError("Directory unavailable")
                body = bytearray()
                for chunk in response.iter_bytes(chunk_size=4096):
                    body.extend(chunk)
                    if len(body) > 131072:
                        raise ValueError("Oversized directory")
                data = json.loads(body)
            if (not isinstance(data, dict) or data.get("company_id") != str(self._company)
                    or data.get("complete") is not True
                    or not isinstance(data.get("employees"), list)
                    or len(data["employees"]) > limit):
                raise ValueError("Incomplete or unverified directory")
            result, seen = [], set()
            for row in data["employees"]:
                if (not isinstance(row, dict)
                        or row.get("company_id") != str(self._company)
                        or type(row.get("active")) is not bool
                        or not isinstance(row.get("role"), str)):
                    raise ValueError("Invalid membership")
                identifier = UUID(row["employee_id"])
                if identifier in seen:
                    raise ValueError("Ambiguous membership")
                seen.add(identifier)
                result.append(VerifiedStaffIdentity(identifier, self._company,
                    row["role"], row["active"], frozenset()))
            return tuple(result)

        try:
            if self._client is not None:
                return read(self._client)
            with httpx.Client(trust_env=False, follow_redirects=False) as client:
                return read(client)
        except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
            raise ValueError("Verified employee directory unavailable") from None
