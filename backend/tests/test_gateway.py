from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_health_is_liveness_only():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_all_capabilities_default_disabled():
    response = client.get("/api/v1/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "integration_disabled"
    assert len(data["capabilities"]) == 5
    assert all(enabled is False for enabled in data["capabilities"].values())


def test_financial_routes_fail_closed_with_no_fake_data():
    for method, path in (
        ("GET", "/api/v1/me/loans"),
        ("POST", "/api/v1/loans/applications"),
        ("POST", "/api/v1/payments/intents"),
        ("GET", "/api/v1/me/wallet"),
    ):
        response = client.request(method, path, json={} if method == "POST" else None)
        assert response.status_code == 503
        assert response.json()["code"] == "INTEGRATION_DISABLED"
        assert response.headers["cache-control"] == "no-store"
        assert "balance" not in response.text.lower()
        assert "approved" not in response.text.lower()


def test_no_openapi_or_debug_docs_on_preview_gateway():
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
