"""Read-only LoanHub borrower/tenant ownership resolver (not bootstrapped).

Grounded in LoanHub's users.id -> borrowers.user_id -> client_company_loan
borrower_id/company_id relationship. Only an existing loan from the approved
tenant establishes tenant ownership; a global borrower profile alone does not.

A separate, least-privileged LoanHub PostgreSQL connection is required.
This does NOT read or manage customer login credentials, access tokens or loans.
"""
from __future__ import annotations

from typing import Callable
from uuid import UUID

import psycopg


class LoanHubBorrowerMappingResolver:
    """Resolve a VERIFIED LoanHub user id to an existing tenant borrower.

    Never accept a tenant from the browser. Configure one trusted tenant
    during backend bootstrap and use a SELECT-only PostgreSQL role, separate
    from Batlokoa's own session database connection.
    """

    def __init__(
        self,
        *,
        tenant_id: str,
        connect: Callable[[], psycopg.Connection],
    ) -> None:
        self._tenant_id = str(UUID(tenant_id))
        if not callable(connect):
            raise ValueError("Trusted read-only LoanHub database provider required")
        self._connect = connect

    def __call__(self, user_id: str) -> tuple[str, str] | None:
        try:
            user = UUID(user_id)
            with self._connect() as connection:
                # The DB role must be SELECT-only; the transaction reinforces
                # that contract even if configuration drifts.
                connection.execute("SET TRANSACTION READ ONLY")
                rows = connection.execute(
                    """
                    SELECT DISTINCT b.id
                    FROM users AS u
                    JOIN borrowers AS b ON b.user_id = u.id
                    JOIN client_company_loan AS l ON l.borrower_id = b.id
                    JOIN loan_companies AS c ON c.id = l.company_id
                    WHERE u.id = %s
                      AND l.company_id = %s
                      AND UPPER(u.role::text) = 'BORROWER'
                      AND u.is_active IS TRUE
                      AND u.is_verified IS TRUE
                      AND c.is_active IS TRUE
                    LIMIT 2
                    """,
                    (user, UUID(self._tenant_id)),
                ).fetchall()
            if len(rows) != 1:
                return None
            return (self._tenant_id, str(UUID(str(rows[0][0]))))
        except (ValueError, TypeError, psycopg.Error):
            return None
        except Exception:
            # Fail closed on unavailable or misconfigured private DB driver.
            return None
