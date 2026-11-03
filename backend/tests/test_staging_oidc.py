from dataclasses import replace
from uuid import UUID

import pytest

from backend.app.oidc_discovery import parse_discovery
from backend.app.staging_oidc import (
    ApprovedStagingRegistration, StagingNotReady,
    validate_staging_registration,
)

ISSUER = "https://auth.ithute.co.ls"
ORIGIN = "https://batlokoa.co.ls"
TENANT = UUID("d921126e-e1a7-482e-ad1b-6e99b1682e19")


def metadata():
    return parse_discovery({
        "issuer": ISSUER,
        "authorization_endpoint": ISSUER + "/oauth/authorize",
        "token_endpoint": ISSUER + "/oauth/token",
        "jwks_uri": ISSUER + "/.well-known/jwks.json",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
    }, expected_issuer=ISSUER)


def registration():
    return ApprovedStagingRegistration(
        issuer=ISSUER,
        client_id="batlokoa",
        public_origin=ORIGIN,
        registered_callback=ORIGIN + "/api/v1/auth/callback",
        batlokoa_tenant_id=TENANT,
        registered_by_operator=True,
        issuer_metadata_reviewed=True,
    )


def test_reviewed_staging_plan_never_activates_financial_services():
    plan = validate_staging_registration(registration(), metadata())
    assert plan.client_id == "batlokoa"
    assert plan.redirect_uri == ORIGIN + "/api/v1/auth/callback"
    assert plan.tenant_id == TENANT
    assert plan.financial_access_enabled is False


@pytest.mark.parametrize("mutate", [
    lambda r: replace(r, registered_by_operator=False),
    lambda r: replace(r, issuer_metadata_reviewed=False),
    lambda r: replace(r, issuer="https://unexpected.test"),
    lambda r: replace(r, client_id="loanhub"),
    lambda r: replace(r, client_id=""),
    lambda r: replace(r, public_origin="http://batlokoa.co.ls"),
    lambda r: replace(r, public_origin="https://evil.test"),
    lambda r: replace(r, registered_callback="https://evil.test/api/v1/auth/callback"),
    lambda r: replace(r, registered_callback=ORIGIN + "/other/path"),
])
def test_missing_approval_or_callback_mismatch_blocks_staging(mutate):
    with pytest.raises(StagingNotReady):
        validate_staging_registration(mutate(registration()), metadata())


def test_borrower_proof_not_inferred_from_oidc_readiness():
    approved = replace(registration(), proof_of_borrower_link_reviewed=False)
    plan = validate_staging_registration(approved, metadata())
    assert not plan.financial_access_enabled
