"""Access notification relay and dispatch regression tests; no live sends."""
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4
import json

import httpx
import pytest

from backend.app.staff_access_notification_queue import AccessDeliveryClaim
from backend.app.staff_access_relay_provider import AccessRelayProvider
from backend.app.staff_access_dispatch_worker import AccessDispatchWorker
from backend.app.staff_attendance_dispatch_worker import DispatchOutcome


@pytest.fixture
def claim():
    return AccessDeliveryClaim(uuid4(), uuid4(), uuid4(), uuid4(),
        "reported_login_outside", datetime.now(timezone.utc), uuid4(), 1)


def send(claim, handler, *, key=None):
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = AccessRelayProvider(origin="https://relay.example.test",
            company_id=claim.company_id, token="synthetic-token", client=client)
        return provider.send(claim, idempotency_key=key or claim.idempotency_key)


@pytest.mark.parametrize("kind", ["reported_login_outside", "staff_logged_out"])
def test_relay_minimal_payload_and_receipt(claim, kind):
    claim = replace(claim, event_type=kind,
        branch_id=None if kind == "staff_logged_out" else claim.branch_id)
    def handler(request):
        assert request.url.path == "/api/v1/attendance/access-notifications"
        assert request.headers["Authorization"] == "Bearer synthetic-token"
        assert request.headers["Idempotency-Key"] == claim.idempotency_key
        assert json.loads(request.content) == {
            "company_id": str(claim.company_id), "event_id": str(claim.event_id),
            "employee_id": str(claim.employee_id),
            "branch_id": str(claim.branch_id) if claim.branch_id else None,
            "event_type": kind, "observed_at": claim.observed_at.isoformat()}
        return httpx.Response(202, json={"status": "accepted",
            "company_id": str(claim.company_id), "idempotency_key": claim.idempotency_key})
    assert send(claim, handler) is DispatchOutcome.ACCEPTED


@pytest.mark.parametrize("scenario", ["wrong_company", "wrong_key", "redirect",
    "oversized", "bad_json", "server_error"])
def test_relay_ambiguous_response_never_acknowledges(claim, scenario):
    calls = []
    def handler(request):
        calls.append(request)
        receipt = {"status": "accepted", "company_id": str(claim.company_id),
                   "idempotency_key": claim.idempotency_key}
        if scenario == "wrong_company":
            receipt["company_id"] = str(uuid4())
        elif scenario == "wrong_key":
            receipt["idempotency_key"] = "wrong"
        elif scenario == "redirect":
            return httpx.Response(307, headers={"Location": "https://foreign.example.test"})
        elif scenario == "oversized":
            receipt["padding"] = "x" * 5000
        elif scenario == "bad_json":
            return httpx.Response(200, content=b"{", headers={"Content-Type": "application/json"})
        elif scenario == "server_error":
            return httpx.Response(503)
        return httpx.Response(200, json=receipt)
    assert send(claim, handler) is DispatchOutcome.RETRY
    assert len(calls) == 1


def test_relay_rejects_invalid_claims_before_network(claim):
    def handler(request):
        pytest.fail("Unexpected network request")
    assert send(claim, handler, key="wrong") is DispatchOutcome.REJECTED
    assert send(replace(claim, branch_id=None), handler) is DispatchOutcome.REJECTED
    assert send(replace(claim, event_type="unknown"), handler) is DispatchOutcome.REJECTED
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = AccessRelayProvider(origin="https://relay.example.test",
            company_id=uuid4(), token="synthetic-token", client=client)
        assert provider.send(claim, idempotency_key=claim.idempotency_key) is DispatchOutcome.REJECTED


@pytest.mark.parametrize("outcome,expected", [
    (DispatchOutcome.ACCEPTED, (1, 0, 0)),
    (DispatchOutcome.RETRY, (0, 1, 0)),
    (DispatchOutcome.RECIPIENT_UNAVAILABLE, (0, 1, 0)),
    (DispatchOutcome.REJECTED, (0, 0, 1)),
])
def test_dispatch_outcomes(claim, outcome, expected):
    calls = []
    class Queue:
        def enqueue(self, *, limit):
            return 1
        def claim(self):
            if calls:
                return None
            calls.append("claim")
            return claim
        def acknowledge(self, item):
            assert item == claim
            calls.append("ack")
            return True
        def fail(self, item, *, code, permanent):
            assert item == claim
            assert permanent == (outcome is DispatchOutcome.REJECTED)
            calls.append(code)
            return True
    class Provider:
        def send(self, item, *, idempotency_key):
            assert item == claim and idempotency_key == claim.idempotency_key
            return outcome
    worker = AccessDispatchWorker(Queue(), Provider())
    assert worker.run_once().enqueued == 0
    assert not calls
    report = AccessDispatchWorker(Queue(), Provider(), enabled=True).run_once()
    assert (report.accepted, report.deferred, report.rejected) == expected
    assert ("ack" in calls) == (outcome is DispatchOutcome.ACCEPTED)
