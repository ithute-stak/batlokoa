"""Explicit staging readiness gate for !thute Auth, not a runtime activator.

Only a human-reviewed, registered Batlokoa OIDC client may pass this gate.
It deliberately cannot modify app.state or turn on live customer endpoints.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from .oidc_discovery import VerifiedOidcMetadata


class StagingNotReady(Exception):
    pass


@dataclass(frozen=True)
class ApprovedStagingRegistration:
    issuer: str
    client_id: str
    public_origin: str
    registered_callback: str
    batlokoa_tenant_id: UUID
    registered_by_operator: bool
    issuer_metadata_reviewed: bool
    proof_of_borrower_link_reviewed: bool = False


@dataclass(frozen=True)
class VerifiedStagingPlan:
    issuer: str
    client_id: str
    redirect_uri: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    tenant_id: UUID
    financial_access_enabled: bool = False


def validate_staging_registration(
    registration: ApprovedStagingRegistration,
    metadata: VerifiedOidcMetadata,
) -> VerifiedStagingPlan:
    """Ensure no inferred callback URL, audience, tenant or endpoint is accepted."""
    if not registration.registered_by_operator or not registration.issuer_metadata_reviewed:
        raise StagingNotReady("OIDC client approval and issuer review are required")
    if registration.issuer != metadata.issuer or not registration.client_id:
        raise StagingNotReady("OIDC client or issuer is not verified")
    if registration.client_id.lower() == "loanhub":
        raise StagingNotReady("Do not use the LoanHub client audience for Batlokoa")
    origin = urlsplit(registration.public_origin)
    callback = registration.public_origin.rstrip("/") + "/api/v1/auth/callback"
    if (origin.scheme != "https" or not origin.hostname or origin.path not in ("", "/")
            or origin.username or origin.password or origin.query or origin.fragment
            or registration.registered_callback != callback):
        raise StagingNotReady("Callback must exactly match the registered HTTPS origin")
    if not isinstance(registration.batlokoa_tenant_id, UUID):
        raise StagingNotReady("Tenant identity must be server-approved")
    if "none" not in metadata.token_endpoint_auth_methods_supported:
        raise StagingNotReady("Current token exchanger requires an approved public client")
    # Borrower proof approval is an independent production financial-access gate.
    # Even if checked, passing this function never enables financial operations.
    return VerifiedStagingPlan(
        issuer=registration.issuer,
        client_id=registration.client_id,
        redirect_uri=registration.registered_callback,
        authorization_endpoint=metadata.authorization_endpoint,
        token_endpoint=metadata.token_endpoint,
        jwks_uri=metadata.jwks_uri,
        tenant_id=registration.batlokoa_tenant_id,
    )
