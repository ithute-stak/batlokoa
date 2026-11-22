"""Adversarial contract checks for read-only registration release inspection.

No test enables a client creation pathway or uses a live LoanHub endpoint.
"""
from uuid import uuid4

import httpx
import pytest

from backend.app.loanhub_registration_release_status import (
    LoanHubRegistrationReleaseStatus,
    RegistrationReleaseStatusUnavailable,
)
from backend.app.staff_authorization import StaffAccessDenied, VerifiedStaffIdentity

LOANHUB = "https://loanhub-contract.example"


def verified_staff():
    return VerifiedStaffIdentity(
        user_id=uuid4(), company_id=uuid4(), role="LOAN_OFFICER",
        active=True, branch_ids=frozenset({uuid4()}),
    )


def payload():
    return {
        "new_only_registration_available": True,
        "can_submit_new_only_registration": True,
        "requires_identity_migration_approval": False,
        "requires_independent_release_approval": False,
        "reason_code": "AVAILABLE",
    }


def check(handler, *, staff=None, token="session-token"):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        adapter = LoanHubRegistrationReleaseStatus(origin=LOANHUB, client=client)
        return adapter.inspect(
            staff=verified_staff() if staff is None else staff,
            access_token=token,
        )
    finally:
        client.close()


@pytest.mark.parametrize("origin", [
    "http://loanhub-contract.example",
    "https://user:pass@loanhub-contract.example",
    "https://loanhub-contract.example/other",
    "https://loanhub-contract.example/?role=admin",
    "https://loanhub-contract.example/#fragment",
    "not-an-origin",
])
def test_untrusted_origins_are_rejected(origin):
    with pytest.raises(ValueError, match="Pinned HTTPS"):
        LoanHubRegistrationReleaseStatus(origin=origin)


@pytest.mark.parametrize("token", ["", "has space", "line\nbreak", "x" * 8193])
def test_invalid_access_tokens_are_rejected_before_network(token):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload())
    with pytest.raises(StaffAccessDenied):
        check(handler, token=token)
    assert calls == []


def test_unverified_identity_is_rejected_before_network():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload())
    with pytest.raises(StaffAccessDenied):
        check(handler, staff="browser-supplied-role")
    assert calls == []


@pytest.mark.parametrize("response", [
    httpx.Response(302, headers={"location": "https://untrusted.example/collect"}),
    httpx.Response(200, text="not-json"),
    httpx.Response(200, json=["not", "an", "object"]),
    httpx.Response(200, json={"can_submit_new_only_registration": True}),
    httpx.Response(200, json=payload() | {"new_only_registration_available": 1}),
    httpx.Response(200, json=payload() | {"reason_code": 12}),
    httpx.Response(200, content=b"x" * 8193, headers={"content-type": "application/json"}),
    httpx.Response(401, json=payload()),
    httpx.Response(503, json=payload()),
])
def test_unexpected_upstream_responses_never_release_registration(response):
    with pytest.raises(RegistrationReleaseStatusUnavailable):
        check(lambda request: response)


def test_network_failure_never_releases_registration():
    def offline(request):
        raise httpx.ConnectError("upstream offline", request=request)
    with pytest.raises(RegistrationReleaseStatusUnavailable):
        check(offline)


def test_future_true_upstream_flag_still_denies_client_creation():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload())
    status = check(handler)
    assert status.can_submit is False
    assert status.state == "not_released"
    assert status.requires_identity_migration_approval is True
    assert status.requires_independent_release_approval is True
    assert len(calls) == 1
    assert calls[0].method == "GET"
    assert calls[0].url.path == "/api/v1/batlokoa/registration/availability"
    assert calls[0].headers["cache-control"] == "no-store"
    assert "session-token" not in str(calls[0].url)
