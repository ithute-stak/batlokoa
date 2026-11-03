"""Read-only customer loan orchestration (not an enabled HTTP API).

Security boundary:
- A cryptographically verified subject must match a server-owned customer map.
- Tenant ID must come from protected service configuration, never request args.
- Only a read-only adapter is accepted; no financial mutations exist here.
- Invalid upstream data fails the whole request instead of displaying fake loans.
"""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from .contracts import LoanHubAdapter, LoanSummary
from .identity import CustomerDirectory, VerifiedClaims, resolve_customer


class LoanReadUnavailable(Exception):
    """Missing/invalid identity mapping or downstream availability."""


class LoanReadForbidden(Exception):
    """Caller is not mapped to the configured Batlokoa tenant."""


@dataclass(frozen=True)
class LoanReadService:
    tenant_id: str
    directory: CustomerDirectory
    adapter: LoanHubAdapter
    max_loans: int = 100

    async def list_my_loans(self, *, claims: VerifiedClaims) -> list[LoanSummary]:
        if not self.tenant_id or not 1 <= self.max_loans <= 1000:
            raise LoanReadUnavailable("Read-only service is not safely configured")

        customer = await resolve_customer(
            claims=claims, directory=self.directory,
            permitted_tenant_id=self.tenant_id,
        )
        if customer is None:
            # Do not disclose whether a customer exists in another tenant.
            raise LoanReadForbidden("Customer access is not authorized")

        try:
            records = await self.adapter.list_customer_loans(
                tenant_id=customer.tenant_id,
                customer_id=customer.customer_id,
            )
            if not isinstance(records, list) or len(records) > self.max_loans:
                raise LoanReadUnavailable("Loan service returned an invalid result")
            loans = [LoanSummary.model_validate(row) for row in records]
            ids = [row.loan_id for row in loans]
            if len(ids) != len(set(ids)):
                raise LoanReadUnavailable("Loan service returned duplicate loan IDs")
            return loans
        except (ValidationError, TypeError, ValueError) as exc:
            raise LoanReadUnavailable("Loan service returned an invalid result") from exc
