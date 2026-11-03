"""Read-only PostgreSQL staging schema preflight.

This is a readiness probe for a privileged deployment pipeline, not a migration
runner. It cannot create tables, change roles, or activate customer endpoints.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import asyncpg


@dataclass(frozen=True)
class SchemaPreflight:
    ready: bool
    missing_relations: tuple[str, ...]
    missing_constraints: tuple[str, ...]


RELATIONS = (
    "customer_account_links",
    "customer_account_link_events",
    "customer_sessions",
    "customer_central_session_revocations",
    "oidc_login_transactions",
)

# Check semantics of the hard-required PK/FK/unique relations, not only
# existence of a schema containing similarly named empty tables.
CONSTRAINTS = (
    ("customer_account_links", "p", "customer_account_links_pkey"),
    ("customer_account_links", "u", "uq_batlokoa_auth_identity"),
    ("customer_account_links", "u", "uq_batlokoa_tenant_borrower"),
    ("customer_account_links", "u", "customer_account_links_proof_sha256_key"),
    ("customer_account_links", "u", "customer_account_links_consent_sha256_key"),
    ("customer_account_link_events", "f", "customer_account_link_events_link_id_fkey"),
    ("customer_sessions", "f", "customer_sessions_link_id_fkey"),
    ("customer_sessions", "u", "customer_sessions_token_sha256_key"),
    ("customer_central_session_revocations", "p", "customer_central_session_revocations_pkey"),
    ("oidc_login_transactions", "p", "oidc_login_transactions_pkey"),
)


async def inspect_staging_schema(
    pool: asyncpg.Pool, *, schema: str = "public"
) -> SchemaPreflight:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema):
        raise ValueError("Invalid schema name")
    async with pool.acquire() as conn:
        present = await conn.fetch(
            """SELECT c.relname AS name FROM pg_class c
               JOIN pg_namespace n ON n.oid=c.relnamespace
               WHERE n.nspname=$1 AND c.relkind IN ('r','p')
                 AND c.relname = ANY($2::text[])""",
            schema, list(RELATIONS),
        )
        constraints = await conn.fetch(
            """SELECT c.relname AS relation, co.contype AS kind, co.conname AS name
               FROM pg_constraint co
               JOIN pg_class c ON c.oid=co.conrelid
               JOIN pg_namespace n ON n.oid=c.relnamespace
               WHERE n.nspname=$1 AND c.relname = ANY($2::text[])""",
            schema, list(RELATIONS),
        )
    tables = {row["name"] for row in present}
    keys = {(row["relation"], (row["kind"].decode("ascii") if isinstance(row["kind"], bytes) else row["kind"]), row["name"]) for row in constraints}
    missing_relations = tuple(r for r in RELATIONS if r not in tables)
    missing_constraints = tuple(
        f"{relation}.{name}" for relation, kind, name in CONSTRAINTS
        if (relation, kind, name) not in keys
    )
    return SchemaPreflight(
        ready=not missing_relations and not missing_constraints,
        missing_relations=missing_relations,
        missing_constraints=missing_constraints,
    )
