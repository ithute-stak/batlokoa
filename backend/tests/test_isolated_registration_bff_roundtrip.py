"""Full synthetic Batlokoa BFF -> LoanHub HTTP contract rehearsal.

Tests mount the normally unmounted BFF route only inside a temporary
FastAPI TestClient and intercept both POST and GET with httpx.MockTransport.
No network, customer database or production route is ever touched.
"""
from uuid import uuid4

import httpx

from backend.app import staff_client_creation_routes as routes
from backend.tests.test_staged_save_client_http_boundary import (
    ACTOR, BRANCH, COMPANY, PATH, body, headers, isolated_client,
)


def test_isolated_bff_post_then_verified_readback_and_idempotent_retry(monkeypatch):
    account = uuid4()
    calls = []
    registrations = set()

    def upstream(request):
        assert request.url.host == "loanhub.test"
        assert request.headers["authorization"] == "Bearer synthetic-never-real-jwt"
        assert request.headers["x-company-id"] == str(COMPANY)
        calls.append((request.method, request.url.path))
        if request.method == "POST":
            assert request.url.path == "/api/v1/batlokoa/registration/clients"
            assert request.headers["idempotency-key"] == "synthetic-save-request-00001"
            assert request.headers["cache-control"] == "no-store"
            assert request.headers["content-type"] == "application/json"
            import json
            assert json.loads(request.content) == body()
            key = request.headers["idempotency-key"]
            replayed = key in registrations
            registrations.add(key)
            return httpx.Response(
                201, json={"client_account_id": str(account), "replayed": replayed})
        assert request.method == "GET"
        assert request.url.path == "/api/v1/company-clients/" + str(account)
        assert request.headers["x-active-role"] == "loan_officer"
        return httpx.Response(200, json={
            "id": str(account), "company_id": str(COMPANY),
            "branch_id": str(BRANCH), "opened_by_user_id": str(ACTOR),
            "source": "new_only_registration",
        })

    # Save the real httpx.Client constructor before replacing routes' module
    # reference. Use the isolated in-memory transport for every upstream call.
    real_client = httpx.Client
    transport = httpx.MockTransport(upstream)
    monkeypatch.setattr(
        routes.httpx, "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    browser = isolated_client(monkeypatch, released=True)
    first = browser.post(PATH, headers=headers(), json=body())
    assert first.status_code == 201
    assert first.json() == {
        "registered": True, "client_account_id": str(account),
        "replayed": False,
    }
    repeat = browser.post(PATH, headers=headers(), json=body())
    assert repeat.status_code == 201
    assert repeat.json() == {
        "registered": True, "client_account_id": str(account),
        "replayed": True,
    }
    assert calls == [
        ("POST", "/api/v1/batlokoa/registration/clients"),
        ("GET", "/api/v1/company-clients/" + str(account)),
        ("POST", "/api/v1/batlokoa/registration/clients"),
        ("GET", "/api/v1/company-clients/" + str(account)),
    ]


def test_isolated_bff_rejects_wrong_tenant_readback(monkeypatch):
    account = uuid4()
    calls = []

    def upstream(request):
        calls.append(request.method)
        if request.method == "POST":
            return httpx.Response(201, json={
                "client_account_id": str(account), "replayed": False,
            })
        return httpx.Response(200, json={
            "id": str(account), "company_id": str(uuid4()),
            "branch_id": str(BRANCH), "opened_by_user_id": str(ACTOR),
            "source": "new_only_registration",
        })

    real_client = httpx.Client
    transport = httpx.MockTransport(upstream)
    monkeypatch.setattr(
        routes.httpx, "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    browser = isolated_client(monkeypatch, released=True)
    response = browser.post(PATH, headers=headers(), json=body())
    assert response.status_code == 503
    assert response.json() == {"code": "REGISTRATION_NOT_CONFIRMED"}
    assert calls == ["POST", "GET"]


def test_isolated_bff_requires_readback_even_when_upstream_post_succeeds(monkeypatch):
    account = uuid4()
    calls = []

    def upstream(request):
        calls.append(request.method)
        if request.method == "POST":
            return httpx.Response(201, json={
                "client_account_id": str(account), "replayed": False,
            })
        return httpx.Response(404, json={"detail": "not found"})

    real_client = httpx.Client
    transport = httpx.MockTransport(upstream)
    monkeypatch.setattr(
        routes.httpx, "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    browser = isolated_client(monkeypatch, released=True)
    response = browser.post(PATH, headers=headers(), json=body())
    assert response.status_code == 503
    assert response.json() == {"code": "REGISTRATION_NOT_CONFIRMED"}
    assert calls == ["POST", "GET"]


def test_disabled_live_gate_never_enters_transport_even_if_supplied(monkeypatch):
    def forbidden(request):
        raise AssertionError("Disabled route must never contact LoanHub")

    real_client = httpx.Client
    transport = httpx.MockTransport(forbidden)
    monkeypatch.setattr(
        routes.httpx, "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    browser = isolated_client(monkeypatch, released=False)
    response = browser.post(PATH, headers=headers(), json=body())
    assert response.status_code == 503
    assert response.json() == {"code": "NEW_ONLY_REGISTRATION_NOT_RELEASED"}
