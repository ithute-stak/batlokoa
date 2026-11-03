from fastapi.testclient import TestClient

from pydantic import ValidationError
import pytest

from backend.app.contracts import Money, PaymentIntentRequest
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

def test_financial_contract_uses_lsl_minor_units_and_rejects_unknown_fields():
    assert Money(currency="LSL", minor_units=1234).minor_units == 1234
    for payload in (
        {"currency": "USD", "minor_units": 1234},
        {"currency": "LSL", "minor_units": -1},
        {"currency": "LSL", "minor_units": 100, "secret": "must not accept"},
    ):
        with pytest.raises(ValidationError):
            Money(**payload)


def test_payment_intent_requires_idempotency_key_and_positive_minor_units():
    with pytest.raises(ValidationError):
        PaymentIntentRequest(loan_id="loan-1", amount_minor_units=100, idempotency_key="short")
    with pytest.raises(ValidationError):
        PaymentIntentRequest(loan_id="loan-1", amount_minor_units=0, idempotency_key="0123456789abcdef")
    valid = PaymentIntentRequest(loan_id="loan-1", amount_minor_units=100, idempotency_key="0123456789abcdef")
    assert valid.amount_minor_units == 100
