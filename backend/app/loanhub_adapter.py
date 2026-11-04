"""LoanHub v2 read-only HTTP adapter, deliberately not registered in the API.

Verified against LoanHub source:
- apps/backend/main.py mounts the router at /api/v1
- apps/backend/routers/loans.py exposes GET /loans/
- borrower-role tokens cause server-side borrower filtering
- database/schemas/loan.py includes id, company_id, borrower_id, balance, status.

The supplied credential MUST be a LoanHub borrower-scoped access token
associated with the already verified server-side customer mapping. Never
supply an admin/service token here: unlike a borrower token, that might have
broader access and is not suitable for a customer-facing lookup.
"""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Callable
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from .contracts import LoanSummary, Money


class LoanHubReadError(Exception):
    """No upstream response may be presented as an authoritative loan balance."""


def _minor_units(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str, Decimal)):
        raise LoanHubReadError("Invalid LoanHub amount")
    try:
        decimal = Decimal(str(value))
        if not decimal.is_finite() or decimal < 0:
            raise LoanHubReadError("Invalid LoanHub amount")
        cents = decimal * 100
        if cents != cents.to_integral_value():
            raise LoanHubReadError("LoanHub amount has fractional cents")
        amount = int(cents)
        Money(currency="LSL", minor_units=amount)
        return amount
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise LoanHubReadError("Invalid LoanHub amount") from exc


def _parse_loanhub_loans(payload: object, *, company_id: UUID, borrower_id: UUID) -> list[LoanSummary]:
    if not isinstance(payload, list) or len(payload) >= 100:
        raise LoanHubReadError("Unexpected or truncated LoanHub loan list")
    loans: list[LoanSummary] = []
    identifiers: set[str] = set()
    for row in payload:
        if not isinstance(row, dict):
            raise LoanHubReadError("Invalid LoanHub record")
        try:
            if UUID(str(row["company_id"])) != company_id or UUID(str(row["borrower_id"])) != borrower_id:
                raise LoanHubReadError("LoanHub returned another tenant or borrower")
            loan_id = str(UUID(str(row["id"])))
            if loan_id in identifiers:
                raise LoanHubReadError("Duplicate loan record")
            identifiers.add(loan_id)
            status = row["status"]
            if not isinstance(status, str) or not status:
                raise LoanHubReadError("Invalid LoanHub loan status")
            loans.append(LoanSummary(
                loan_id=loan_id,
                status=status,
                outstanding=Money(currency="LSL", minor_units=_minor_units(row["balance"])),
            ))
        except (KeyError, TypeError, ValueError) as exc:
            raise LoanHubReadError("Invalid LoanHub loan record") from exc
    return loans


class LoanHubBorrowerReadAdapter:
    """Strict read-only adapter for an already provisioned borrower identity.

    The bearer supplier is backend-owned. No credential is read from Flutter,
    incoming HTTP parameters, query strings, or caller-supplied tenant headers.
    """

    def __init__(
        self,
        *,
        base_url: str,
        borrower_token_for: Callable[[str, str], str | None],
        client: httpx.AsyncClient | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        if (parsed.scheme != "https" or not parsed.hostname or
                parsed.username or parsed.password or parsed.query or parsed.fragment or
                parsed.path not in ("", "/")):
            raise ValueError("LoanHub base URL must be an HTTPS origin without credentials or paths")
        self._origin = base_url.rstrip("/")
        self._token_for = borrower_token_for
        self._client = client

    async def list_customer_loans(self, *, tenant_id: str, customer_id: str) -> list[LoanSummary]:
        try:
            company_uuid = UUID(tenant_id)
            borrower_uuid = UUID(customer_id)
        except (TypeError, ValueError) as exc:
            raise LoanHubReadError("Invalid mapped LoanHub identity") from exc

        # Credential resolution must be backend-owned and borrower-specific.
        # A revoked/expired/absent grant must return None without HTTP access.
        try:
            token = self._token_for(str(company_uuid), str(borrower_uuid))
        except Exception as exc:
            raise LoanHubReadError("Borrower credential is unavailable") from exc
        if not token or not isinstance(token, str) or len(token) > 8192 or any(ch.isspace() for ch in token):
            raise LoanHubReadError("No approved borrower-scoped LoanHub session")

        async def call(client: httpx.AsyncClient) -> httpx.Response:
            try:
                return await client.get(
                    f"{self._origin}/api/v1/loans/",
                    params={"skip": 0, "limit": 100},
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                        "Cache-Control": "no-store",
                    },
                    timeout=5,
                    follow_redirects=False,
                )
            except httpx.HTTPError as exc:
                raise LoanHubReadError("LoanHub is unavailable") from exc

        if self._client is None:
            async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as client:
                response = await call(client)
        else:
            response = await call(self._client)

        if response.status_code != 200:
            raise LoanHubReadError("LoanHub returned an unsuccessful response")
        if len(response.content) > 2_000_000:
            raise LoanHubReadError("LoanHub response exceeded size limit")
        try:
            payload = json.loads(response.content, parse_float=Decimal)
        except (ValueError, UnicodeDecodeError) as exc:
            raise LoanHubReadError("LoanHub returned invalid JSON") from exc
        return _parse_loanhub_loans(payload, company_id=company_uuid, borrower_id=borrower_uuid)
