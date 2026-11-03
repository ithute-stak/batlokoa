"""PostgreSQL-backed, fail-closed link store and customer directory.

NOT instantiated from the customer-facing application. Requires a separately
provisioned, least-privilege asyncpg pool and schema migration. No password,
authentication token, NID, phone, or plaintext consent/proof reference is stored.

Unique indexes permanently reserve linked subjects/borrowers, including after
revocation. Relinking requires a separately audited recovery design.
"""
from __future__ import annotations

import hashlib
import re
from uuid import UUID, uuid4

import asyncpg

from .account_linking import LinkConflict, LinkDenied
from .identity import CustomerContext


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class PostgresCustomerLinkStore:
    def __init__(self, pool: asyncpg.Pool, *, schema: str = "public") -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema):
            raise ValueError("Invalid database schema")
        self._pool = pool
        self._links = f'"{schema}".customer_account_links'
        self._events = f'"{schema}".customer_account_link_events'

    async def bind_once(
        self, *, issuer: str, subject: str, tenant_id: UUID,
        borrower_id: UUID, consent_reference: str, proof_id: str,
    ) -> CustomerContext:
        if (not issuer.startswith("https://") or not 1 <= len(subject) <= 255
                or not 1 <= len(consent_reference) <= 128
                or not 1 <= len(proof_id) <= 128):
            raise LinkDenied("Invalid link identity or evidence")
        link_id = uuid4()
        async with self._pool.acquire() as connection:
            try:
                async with connection.transaction():
                    await connection.execute(
                        f"""INSERT INTO {self._links}
                        (id, issuer, subject, tenant_id, borrower_id,
                         proof_sha256, consent_sha256)
                        VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                        link_id, issuer, subject, tenant_id, borrower_id,
                        _digest(proof_id), _digest(consent_reference),
                    )
                    await connection.execute(
                        f"""INSERT INTO {self._events}
                        (id, link_id, event_type, actor_subject, reason)
                        VALUES ($1,$2,'linked',$3,'Customer consent and borrower proof validated')""",
                        uuid4(), link_id, subject,
                    )
            except asyncpg.UniqueViolationError as exc:
                raise LinkConflict("Customer identity or loan account is already linked") from exc
        return CustomerContext(
            tenant_id=str(tenant_id), customer_id=str(borrower_id), auth_subject=subject
        )

    async def lookup(self, *, issuer: str, subject: str) -> CustomerContext | None:
        if not issuer.startswith("https://") or not subject:
            return None
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""SELECT tenant_id, borrower_id, subject
                FROM {self._links}
                WHERE issuer=$1 AND subject=$2 AND revoked_at IS NULL""",
                issuer, subject,
            )
        if row is None:
            return None
        return CustomerContext(
            tenant_id=str(row["tenant_id"]),
            customer_id=str(row["borrower_id"]),
            auth_subject=row["subject"],
        )

    async def revoke_self(
        self, *, issuer: str, subject: str, tenant_id: UUID, reason: str,
    ) -> bool:
        """Revoke a verified subject's own mapping; caller must authenticate them.

        This method is NOT a public route. Runtime caller must supply verified
        subject and trusted tenant_id, never arbitrary browser parameters.
        """
        if (not issuer.startswith("https://") or not subject or
                not 12 <= len(reason.strip()) <= 500):
            raise LinkDenied("Invalid revocation context")
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    f"""UPDATE {self._links}
                    SET revoked_at=now()
                    WHERE issuer=$1 AND subject=$2 AND tenant_id=$3
                      AND revoked_at IS NULL
                    RETURNING id""",
                    issuer, subject, tenant_id,
                )
                if row is None:
                    return False
                await connection.execute(
                    f"""INSERT INTO {self._events}
                    (id, link_id, event_type, actor_subject, reason)
                    VALUES ($1,$2,'revoked',$3,$4)""",
                    uuid4(), row["id"], subject, reason.strip(),
                )
                return True
