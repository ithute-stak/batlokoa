"""Relay contract tests using a synthetic HTTP transport; no live sends."""
import json
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest

from backend.app.staff_attendance_dispatch_worker import DispatchOutcome
from backend.app.staff_attendance_notification_queue import DeliveryClaim
from backend.app.staff_attendance_relay_provider import AttendanceRelayProvider


@pytest.fixture
def claim():
    return DeliveryClaim(1, uuid4(), uuid4(), uuid4(),
                         "reported_outside_perimeter",
                         datetime.now(timezone.utc), uuid4(), 1)


def send(claim, handler, *, company=None, key=None):
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = AttendanceRelayProvider(
            origin="https://relay.example.test",
            company_id=company or claim.company_id,
            token="synthetic-token", client=client)
        return provider.send(claim, idempotency_key=key or claim.idempotency_key)


def receipt(claim, status="accepted", **extra):
    return {"idempotency_key": claim.idempotency_key,
            "company_id": str(claim.company_id), "status": status, **extra}


def test_valid_receipt_and_minimal_payload(claim):
    def handler(request):
        assert str(request.url) == "https://relay.example.test/api/v1/attendance/notifications"
        assert request.method == "POST"
        assert request.headers["Authorization"] == "Bearer synthetic-token"
        assert request.headers["Idempotency-Key"] == claim.idempotency_key
        payload = json.loads(request.content)
        assert payload == {
            "company_id": str(claim.company_id), "alert_id": claim.alert_id,
            "employee_id": str(claim.employee_id), "branch_id": str(claim.branch_id),
            "event_type": claim.event_type, "observed_at": claim.observed_at.isoformat(),
        }
        return httpx.Response(202, json=receipt(claim))
    assert send(claim, handler) is DispatchOutcome.ACCEPTED


def test_scope_and_key_mismatch_do_not_send(claim):
    def handler(_):
        pytest.fail("Unauthorized network request")
    assert send(claim, handler, company=uuid4()) is DispatchOutcome.REJECTED
    assert send(claim, handler, key="wrong-key") is DispatchOutcome.REJECTED


@pytest.mark.parametrize("status,expected", [
    ("recipient_unavailable", DispatchOutcome.RECIPIENT_UNAVAILABLE),
    ("rejected", DispatchOutcome.REJECTED),
    ("unknown", DispatchOutcome.RETRY),
])
def test_explicit_relay_status(claim, status, expected):
    assert send(claim, lambda _: httpx.Response(200, json=receipt(claim, status))) is expected


@pytest.mark.parametrize("response_type", [
    "wrong_key", "wrong_company", "oversized", "malformed", "html", "server_error",
])
def test_invalid_receipts_are_never_accepted(claim, response_type):
    def handler(_):
        if response_type == "wrong_key":
            return httpx.Response(202, json=receipt(claim, idempotency_key="wrong"))
        if response_type == "wrong_company":
            return httpx.Response(202, json=receipt(claim, company_id=str(uuid4())))
        if response_type == "oversized":
            return httpx.Response(202, json=receipt(claim, padding="x"*5000))
        if response_type == "malformed":
            return httpx.Response(202, content=b"{", headers={"Content-Type": "application/json"})
        if response_type == "html":
            return httpx.Response(200, text="<html>accepted</html>")
        return httpx.Response(503, json=receipt(claim))
    assert send(claim, handler) is DispatchOutcome.RETRY


def test_redirect_never_forwards_credentials(claim):
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(307, headers={"Location": "https://untrusted.example.test/"})
    assert send(claim, handler) is DispatchOutcome.RETRY
    assert calls == ["https://relay.example.test/api/v1/attendance/notifications"]


def test_network_timeout_retries(claim):
    def handler(request):
        raise httpx.ReadTimeout("synthetic timeout", request=request)
    assert send(claim, handler) is DispatchOutcome.RETRY


@pytest.mark.parametrize("origin", [
    "http://relay.example.test", "https://user:pass@relay.example.test",
    "https://relay.example.test/path", "https://relay.example.test/?q=1",
    "https://relay.example.test/#fragment",
])
def test_unsafe_origin_rejected(origin, claim):
    with pytest.raises(ValueError):
        AttendanceRelayProvider(origin=origin, company_id=claim.company_id,
                                token="synthetic-token")
