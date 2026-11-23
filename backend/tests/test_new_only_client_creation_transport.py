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

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return httpx.Response(200, json={
            "id": str(ACCOUNT), "company_id": str(COMPANY),
            "branch_id": str(BRANCH),
            "opened_by_user_id": str(ACTOR),
            "source": "new_only_registration",
        })


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
    assert len(client.calls) == 2
    url, opts = client.calls[0]
    assert url == "https://loanhub.test/api/v1/batlokoa/registration/clients"
    assert opts["headers"]["Idempotency-Key"] == "synthetic-request-key-001"
    assert opts["headers"]["X-Company-ID"] == str(COMPANY)
    assert opts["headers"]["Authorization"] == "Bearer synthetic-server-only-token"
    assert "/company-clients" not in url
    read_url, read_opts = client.calls[1]
    assert read_url == ("https://loanhub.test/api/v1/company-clients/" + str(ACCOUNT))
    assert read_opts["headers"]["X-Company-ID"] == str(COMPANY)


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
    "https://loanhub.test\nevil.example",
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


@pytest.mark.parametrize("returned", [
    {"id": str(uuid4()), "company_id": str(COMPANY), "branch_id": str(BRANCH)},
    {"id": str(ACCOUNT), "company_id": str(uuid4()), "branch_id": str(BRANCH)},
    {"id": str(ACCOUNT), "company_id": str(COMPANY), "branch_id": str(uuid4())},
    {"id": str(ACCOUNT), "company_id": str(COMPANY), "branch_id": None},
    {"id": str(ACCOUNT), "company_id": str(COMPANY),
     "branch_id": str(BRANCH), "opened_by_user_id": str(uuid4()),
     "source": "new_only_registration"},
    {"id": str(ACCOUNT), "company_id": str(COMPANY),
     "branch_id": str(BRANCH), "opened_by_user_id": str(ACTOR),
     "source": "assisted_registration"},
])
def test_upstream_readback_must_match_exact_account_company_and_branch(returned):
    class WrongReadback(RecordingClient):
        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return httpx.Response(200, json=returned)
    client = WrongReadback()
    with pytest.raises(ClientCreationUnavailable):
        invoke(client, independently_approved_release=True)
    assert len(client.calls) == 2


def test_unavailable_account_readback_never_reports_registration_success():
    class UnavailableReadback(RecordingClient):
        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return httpx.Response(404, json={"detail": "Not found"})
    client = UnavailableReadback()
    with pytest.raises(ClientCreationUnavailable):
        invoke(client, independently_approved_release=True)
    assert len(client.calls) == 2


def test_replayed_registration_still_requires_same_account_readback():
    client = RecordingClient(json_body={
        "client_account_id": str(ACCOUNT), "replayed": True,
    })
    receipt = invoke(client, independently_approved_release=True)
    assert receipt.replayed is True
    assert receipt.account_id == ACCOUNT
    assert len(client.calls) == 2


def test_post_confirms_account_but_readback_fails_requires_safe_retry():
    class FailedReadback(RecordingClient):
        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return httpx.Response(503, json={"code": "UNAVAILABLE"})
    client = FailedReadback()
    with pytest.raises(ClientCreationUnavailable):
        invoke(client, independently_approved_release=True)
    # The POST might have committed. Caller must retry with its ORIGINAL
    # idempotency key rather than treating the absence of GET as a rollback.
    assert client.calls[0][1]["headers"]["Idempotency-Key"] == (
        "synthetic-request-key-001")
    assert len(client.calls) == 2


def test_authorized_gateway_post_then_new_request_gets_persisted_account():
    """Simulate a separate LoanHub HTTP read after the POST transaction.

    Real PostgreSQL persistence is independently certified in LoanHub CI;
    this ensures Batlokoa checks the exact created UUID, company and branch
    before it considers the submission successful.
    """
    stored = {}

    def loanhub(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer synthetic-server-only-token"
        assert request.headers["x-company-id"] == str(COMPANY)
        if request.method == "POST":
            assert request.url.path == "/api/v1/batlokoa/registration/clients"
            assert request.headers["idempotency-key"] == "synthetic-request-key-001"
            captured = __import__("json").loads(request.content)
            assert captured["branch_id"] == str(BRANCH)
            replay = bool(stored)
            if not replay:
                stored["id"] = str(ACCOUNT)
                stored["company_id"] = str(COMPANY)
                stored["branch_id"] = str(BRANCH)
                stored["opened_by_user_id"] = str(ACTOR)
                stored["source"] = "new_only_registration"
                stored["first_name"] = captured["first_name"]
            return httpx.Response(
                201, json={"client_account_id": str(ACCOUNT),
                           "replayed": replay},
            )
        if request.method == "GET":
            assert request.url.path == (
                "/api/v1/company-clients/" + str(ACCOUNT))
            return httpx.Response(200, json=dict(stored)) if stored else (
                httpx.Response(404, json={"detail": "Not found"}))
        return httpx.Response(405)

    with httpx.Client(transport=httpx.MockTransport(loanhub)) as client:
        first = invoke(client, independently_approved_release=True)
        assert first.account_id == ACCOUNT
        assert first.replayed is False
        second = invoke(client, independently_approved_release=True)
        assert second.account_id == ACCOUNT
        assert second.replayed is True
    assert stored["first_name"] == "Synthetic"
    assert len(stored) == 6


def test_gateway_does_not_claim_save_when_readback_is_wrong():
    def wrong_tenant_response(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, json={
                "client_account_id": str(ACCOUNT), "replayed": False})
        return httpx.Response(200, json={
            "id": str(ACCOUNT), "company_id": str(uuid4()),
            "branch_id": str(BRANCH),
            "opened_by_user_id": str(ACTOR),
            "source": "new_only_registration",
        })

    with httpx.Client(transport=httpx.MockTransport(wrong_tenant_response)) as client:
        with pytest.raises(ClientCreationUnavailable, match="scope readback"):
            invoke(client, independently_approved_release=True)
