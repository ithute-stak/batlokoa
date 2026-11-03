"""No live !thute Auth service is reached by these contract tests."""
import httpx
import pytest

from backend.app.oidc_login import LoginUnavailable
from backend.app.oidc_token_exchange import BackchannelCodeExchanger

URL = "https://auth.example.test/oauth/token"
REDIRECT = "https://batlokoa.example.test/api/v1/auth/callback"
VERIFIER = "v" * 64


def exchanger(handler):
    return BackchannelCodeExchanger(
        token_endpoint=URL,
        client_id="batlokoa",
        expected_redirect_uri=REDIRECT,
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_code_exchange_posts_only_to_pinned_https_endpoint():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200, json={
                "access_token": "a" * 80,
                "id_token": "i" * 80,
                "token_type": "Bearer",
            },
        )

    tokens = await exchanger(handler).exchange(
        code="short-lived-code", code_verifier=VERIFIER, redirect_uri=REDIRECT)
    assert tokens.access_token == "a" * 80
    assert tokens.id_token == "i" * 80
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert str(request.url) == URL
    body = request.content.decode()
    assert "grant_type=authorization_code" in body
    assert "code_verifier=" + VERIFIER in body
    assert "redirect_uri=" in body
    assert "client_id=batlokoa" in body
    assert "access_token" not in body


@pytest.mark.asyncio
@pytest.mark.parametrize("status, payload", [
    (301, {"token_type": "Bearer", "access_token": "a" * 80, "id_token": "i" * 80}),
    (400, {"error": "invalid_grant"}),
    (500, {"error": "temporarily_unavailable"}),
    (200, {"access_token": "a" * 80, "id_token": "i" * 80}),
    (200, {"token_type": "Bearer", "access_token": "short", "id_token": "i" * 80}),
    (200, {"token_type": "Bearer", "access_token": "a" * 80}),
])
async def test_unsuccessful_and_malformed_token_replies_are_denied(status, payload):
    service = exchanger(lambda request: httpx.Response(status, json=payload))
    with pytest.raises(LoginUnavailable):
        await service.exchange(code="code", code_verifier=VERIFIER, redirect_uri=REDIRECT)


@pytest.mark.asyncio
async def test_bad_redirect_never_contacts_token_endpoint():
    calls = []
    service = exchanger(lambda request: calls.append(request) or httpx.Response(200))
    with pytest.raises(LoginUnavailable):
        await service.exchange(
            code="code", code_verifier=VERIFIER,
            redirect_uri="https://attacker.example/callback")
    assert calls == []


@pytest.mark.parametrize("token_url", [
    "http://auth.example.test/token",
    "https://user:pass@auth.example.test/token",
    "https://auth.example.test/token?q=unsafe",
])
def test_untrusted_token_endpoint_rejected(token_url):
    with pytest.raises(ValueError):
        BackchannelCodeExchanger(
            token_endpoint=token_url, client_id="batlokoa",
            expected_redirect_uri=REDIRECT,
        )
