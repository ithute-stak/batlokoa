"""Staging assembly unit tests. No live identity provider or production config."""
from dataclasses import replace
from uuid import UUID

from cryptography.fernet import Fernet
import pytest

from backend.app.main import app
from backend.app.oidc_discovery import parse_discovery
from backend.app.staging_auth_assembly import PinnedSigningKeys, build_staging_auth_assembly
from backend.app.staging_oidc import ApprovedStagingRegistration, StagingNotReady

ISSUER = "https://auth.example.test"
ORIGIN = "https://batlokoa.example.test"


class Keys:
    def get_signing_key_from_jwt(self, token):
        raise AssertionError("No live token verification is allowed")


def metadata():
    return parse_discovery({
        "issuer": ISSUER,
        "authorization_endpoint": ISSUER + "/authorize",
        "token_endpoint": ISSUER + "/token",
        "jwks_uri": ISSUER + "/keys",
        "response_types_supported": ["code"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
    }, expected_issuer=ISSUER)


def registration():
    return ApprovedStagingRegistration(
        issuer=ISSUER, client_id="batlokoa",
        public_origin=ORIGIN,
        registered_callback=ORIGIN + "/api/v1/auth/callback",
        batlokoa_tenant_id=UUID("d921126e-e1a7-482e-ad1b-6e99b1682e19"),
        registered_by_operator=True,
        issuer_metadata_reviewed=True,
    )


def assemble(reg=None, keyuri=ISSUER + "/keys", key=None):
    return build_staging_auth_assembly(
        registration=reg or registration(),
        discovered=metadata(),
        signing_keys=PinnedSigningKeys(keyuri, Keys()),
        pool=object(),
        encryption_key=key if key is not None else Fernet.generate_key(),
    )


def test_complete_staging_configuration_is_composed_but_not_activated():
    a = assemble()
    assert a.plan.financial_access_enabled is False
    assert a.plan.client_id == "batlokoa"
    assert a.auth.login.client_id == "batlokoa"
    assert a.auth.login.redirect_uri == ORIGIN + "/api/v1/auth/callback"
    assert a.auth.login.token_endpoint == ISSUER + "/token"
    assert a.auth.public_origin == ORIGIN
    assert not hasattr(app.state, "auth_route_config")


def test_unreviewed_registration_is_rejected():
    with pytest.raises(StagingNotReady):
        assemble(reg=replace(registration(), issuer_metadata_reviewed=False))


def test_unpinned_jwks_is_rejected():
    with pytest.raises(ValueError):
        assemble(keyuri="https://untrusted.example.test/keys")


def test_invalid_encryption_key_is_rejected():
    with pytest.raises((ValueError, TypeError)):
        assemble(key=b"invalid-key")
