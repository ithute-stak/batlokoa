"""Provider-discovery contract tests: all HTTP responses are mocked."""
import json

import httpx
import pytest

from backend.app.oidc_discovery import (
    DiscoveryUnavailable, OidcDiscoveryClient, parse_discovery,
)

ISSUER = "https://auth.ithute.co.ls"


def metadata(**changes):
    payload = {
        "issuer": ISSUER,
        "authorization_endpoint": ISSUER + "/oauth/authorize",
        "token_endpoint": ISSUER + "/oauth/token",
        "jwks_uri": ISSUER + "/.well-known/jwks.json",
        "id_token_signing_alg_values_supported": ["RS256"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
    }
    payload.update(changes)
    return payload


def test_valid_metadata_is_parsed_without_guessing_actual_provider_support():
    parsed = parse_discovery(metadata(), expected_issuer=ISSUER)
    assert parsed.issuer == ISSUER
    assert parsed.token_endpoint == ISSUER + "/oauth/token"
    assert parsed.jwks_uri == ISSUER + "/.well-known/jwks.json"
    assert parsed.token_endpoint_auth_methods_supported == ("none",)


@pytest.mark.parametrize("changes", [
    {"issuer": "https://lookalike.example.test"},
    {"authorization_endpoint": "http://auth.ithute.co.ls/oauth/authorize"},
    {"authorization_endpoint": "https://attacker.test/authorize"},
    {"token_endpoint": "https://auth.ithute.co.ls.evil.test/token"},
    {"token_endpoint": "https://user:pass@auth.ithute.co.ls/token"},
    {"token_endpoint": "https://auth.ithute.co.ls/token?unsafe=yes"},
    {"jwks_uri": "https://attacker.test/keys"},
    {"jwks_uri": "https://auth.ithute.co.ls/../keys"},
    {"id_token_signing_alg_values_supported": ["none", "HS256"]},
    {"response_types_supported": ["token"]},
    {"grant_types_supported": ["client_credentials"]},
    {"code_challenge_methods_supported": ["plain"]},
    {"token_endpoint_auth_methods_supported": ["client_secret_basic"]},
    {"token_endpoint_auth_methods_supported": None},
])
def test_invalid_or_unsupported_provider_metadata_fails_closed(changes):
    with pytest.raises(DiscoveryUnavailable):
        parse_discovery(metadata(**changes), expected_issuer=ISSUER)


@pytest.mark.asyncio
async def test_fetches_only_pinned_provider_well_known_url():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=metadata())

    client = OidcDiscoveryClient(
        ISSUER, transport=httpx.MockTransport(handler))
    result = await client.fetch()
    assert result.issuer == ISSUER
    assert len(requests) == 1
    assert str(requests[0].url) == ISSUER + "/.well-known/openid-configuration"


@pytest.mark.asyncio
@pytest.mark.parametrize("status,ctype", [
    (302, "application/json"),
    (401, "application/json"),
    (500, "application/json"),
    (200, "text/html"),
])
async def test_non_json_or_error_metadata_fails_closed(status, ctype):
    client = OidcDiscoveryClient(
        ISSUER,
        transport=httpx.MockTransport(lambda req: httpx.Response(
            status, content=json.dumps(metadata()).encode(),
            headers={"content-type": ctype, "location": "https://attacker.test"},
        )),
    )
    with pytest.raises(DiscoveryUnavailable):
        await client.fetch()


@pytest.mark.asyncio
async def test_oversized_discovery_fails_closed():
    client = OidcDiscoveryClient(
        ISSUER, transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200, content=b" " * 65537,
                headers={"content-type": "application/json"},
            )
        ),
    )
    with pytest.raises(DiscoveryUnavailable):
        await client.fetch()


@pytest.mark.asyncio
async def test_untrusted_issuer_never_uses_transport():
    calls = []
    client = OidcDiscoveryClient(
        "http://auth.ithute.co.ls",
        transport=httpx.MockTransport(
            lambda req: calls.append(req) or httpx.Response(200, json=metadata())
        ),
    )
    with pytest.raises(DiscoveryUnavailable):
        await client.fetch()
    assert calls == []
