"""Assemble a reviewed OIDC staging BFF configuration without activating it.

This module does not read environment variables, connect to !thute Auth, run
migrations, change FastAPI app.state or enable live financial services.
Dependencies come exclusively from privileged infrastructure bootstrap.
"""
from __future__ import annotations

from dataclasses import dataclass

import asyncpg
import httpx
from cryptography.fernet import Fernet

from .auth_routes import AuthRouteConfig
from .auth_verification import CentralAuthVerifier, SigningKeySource
from .oidc_discovery import VerifiedOidcMetadata
from .oidc_id_token import OidcIdTokenVerifier
from .oidc_login import OidcLoginService
from .oidc_token_exchange import BackchannelCodeExchanger
from .oidc_transaction_store import PostgresOidcTransactionStore
from .sessions import PostgresSessionStore
from .staging_oidc import (
    ApprovedStagingRegistration, VerifiedStagingPlan,
    validate_staging_registration,
)


@dataclass(frozen=True)
class PinnedSigningKeys:
    """Preconfigured JWKS client; the URL is pinned by operator review.

    In production the 'source' should be a reviewed JWKS client with bounded
    timeouts, cache/key-rotation controls and restricted egress. Do not use a
    signing-key source selected dynamically from user input or JWT headers.
    """
    jwks_uri: str
    source: SigningKeySource


@dataclass(frozen=True)
class StagingAuthAssembly:
    auth: AuthRouteConfig
    plan: VerifiedStagingPlan


def build_staging_auth_assembly(
    *,
    registration: ApprovedStagingRegistration,
    discovered: VerifiedOidcMetadata,
    signing_keys: PinnedSigningKeys,
    pool: asyncpg.Pool,
    encryption_key: bytes,
    exchange_transport: httpx.AsyncBaseTransport | None = None,
) -> StagingAuthAssembly:
    """Compose the already-tested components; never attach them to a public app.

    A real deployer must independently validate the actual IdP registration,
    JWKS client safety and least-privileged database pool. Successful assembly
    is not proof that the login flow, LoanHub or IthutePay are live-ready.
    """
    plan = validate_staging_registration(registration, discovered)
    if signing_keys.jwks_uri != plan.jwks_uri:
        raise ValueError("Signing-key source must match operator-approved JWKS URI")
    if signing_keys.source is None or pool is None:
        raise ValueError("Trusted JWKS provider and persistent DB pool required")
    # Reject missing/invalid Fernet key before building any configured route.
    Fernet(encryption_key)

    keys = signing_keys.source
    access_verifier = CentralAuthVerifier(
        issuer=plan.issuer, audience=plan.client_id, keys=keys
    )
    id_verifier = OidcIdTokenVerifier(
        issuer=plan.issuer, client_id=plan.client_id, keys=keys
    )
    transactions = PostgresOidcTransactionStore(
        pool, encryption_key=encryption_key
    )
    sessions = PostgresSessionStore(pool)
    exchanger = BackchannelCodeExchanger(
        token_endpoint=plan.token_endpoint,
        client_id=plan.client_id,
        expected_redirect_uri=plan.redirect_uri,
        transport=exchange_transport,
    )
    login = OidcLoginService(
        issuer=plan.issuer,
        authorization_endpoint=plan.authorization_endpoint,
        token_endpoint=plan.token_endpoint,
        client_id=plan.client_id,
        redirect_uri=plan.redirect_uri,
        tenant_id=plan.tenant_id,
        verifier=access_verifier,
        transactions=transactions,
        exchanger=exchanger,
        id_token_verifier=id_verifier,
        sessions=sessions,
    )
    auth = AuthRouteConfig(
        login=login, sessions=sessions, public_origin=registration.public_origin
    )
    return StagingAuthAssembly(auth=auth, plan=plan)
