"""Fail-closed tests for Batlokoa's proposed LoanHub new-only transport."""
from uuid import uuid4

import httpx
import pytest

from backend.app.staff_authorization import VerifiedStaffIdentity, StaffAccessDenied
from backend.app.loanhub_new_only_client_creation import (
    ClientCreationNotReleased, ClientCreationUnavailable,
    post_new_only_client,
)

COMPANY, ACTOR, BRANCH, ACCOUNT = (uuid4() for _ in range(4))


def staff(*, role="LOAN_OFFICER"):
    return VerifiedStaffIdentity(
        user_id=ACTOR, company_id=COMPANY, role=role,
        active=True, branch_ids=frozenset({BRANCH}),
    )


class RecordingClient:
    def __init__(self, status=201, json_body=None):
        self.calls = []
        self.status = status
        self.json_body = json_body or {
            "client_account_id": str(ACCOUNT), "replayed": False,
        }

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return httpx.Response(self.status, json=self.json_body)


def payload():
    return {
        "branch_id": str(BRANCH),
        "first_name": "Synthetic",
        "last_name": "Applicant",
        "national_id": "SYNTHETIC-NEVER-REAL-1",
    }


def invoke(client, **overrides):
    kwargs = dict(
        staff=staff(), branch_id=BRANCH,
        loanhub_origin="https://loanhub.test",
        loanhub_access_token="synthetic-server-only-token",
        complete_payload=payload(),
        idempotency_key="synthetic-request-key-001",
        client=client,
    )
    kwargs.update(overrides)
    return post_new_only_client(**kwargs)


def test_default_release_denies_without_any_upstream_request():
    client = RecordingClient()
    with pytest.raises(ClientCreationNotReleased):
        invoke(client)
    assert client.calls == []


def test_explicit_false_release_is_not_authorized_by_browser_payload():
    client = RecordingClient()
    with pytest.raises(ClientCreationNotReleased):
        invoke(client, independently_approved_release=False,
               complete_payload={**payload(), "independently_approved_release": True})
    assert client.calls == []


def test_test_only_authorized_transport_uses_correct_new_only_path():
    client = RecordingClient()
    receipt = invoke(client, independently_approved_release=True)
    assert receipt.account_id == ACCOUNT
    assert receipt.replayed is False
    assert len(client.calls) == 1
    url, opts = client.calls[0]
    assert url == "https://loanhub.test/api/v1/batlokoa/registration/clients"
    assert opts["headers"]["Idempotency-Key"] == "synthetic-request-key-001"
    assert opts["headers"]["X-Company-ID"] == str(COMPANY)
    assert opts["headers"]["Authorization"] == "Bearer synthetic-server-only-token"
    assert "/company-clients" not in url


@pytest.mark.parametrize("changes", [
    {"staff": staff(role="AUDITOR")},
    {"branch_id": uuid4()},
    {"complete_payload": {**payload(), "company_id": str(COMPANY)}},
    {"complete_payload": {**payload(), "branch_id": str(uuid4())}},
    {"idempotency_key": "bad key"},
])
def test_invalid_scope_or_key_rejected_before_upstream(changes):
    client = RecordingClient()
    with pytest.raises((ClientCreationUnavailable, StaffAccessDenied)):
        invoke(client, independently_approved_release=True, **changes)
    assert client.calls == []


def test_unconfirmed_upstream_result_is_not_reported_successful():
    client = RecordingClient(status=503)
    with pytest.raises(ClientCreationUnavailable):
        invoke(client, independently_approved_release=True)
    client = RecordingClient(json_body={"client_account_id": str(ACCOUNT),
                                        "replayed": "false"})
    with pytest.raises(ClientCreationUnavailable):
        invoke(client, independently_approved_release=True)


@pytest.mark.parametrize("origin", [
    "http://loanhub.test",
    "https://loanhub.test.evil.example/path",
    "https://loanhub.test/api",
    "https://loanhub.test?redirect=https://elsewhere.example",
    "https://loanhub.test/#fragment",
    "https://operator:password@loanhub.test",
    "https://loanhub.test:bad-port",
    "https://loanhub.test@evil.example",
    "https://loanhub.test\\nevil.example",
])
def test_untrusted_upstream_origin_never_receives_token_or_identity(origin):
    client = RecordingClient()
    with pytest.raises(ClientCreationUnavailable):
        invoke(client, independently_approved_release=True,
               loanhub_origin=origin)
    assert client.calls == []


def test_valid_https_origin_with_explicit_port_is_preserved():
    client = RecordingClient()
    receipt = invoke(client, independently_approved_release=True,
                     loanhub_origin="https://loanhub.test:8443")
    assert receipt.account_id == ACCOUNT
    assert client.calls[0][0] == (
        "https://loanhub.test:8443/api/v1/batlokoa/registration/clients"
    )
