"""Unmerged, sandbox-only Save Client BFF contract and security tests.

The real gateway app intentionally never mounts the offline POST handler.
All staff, client, and identity values below are synthetic.
"""
import json
from types import MethodType
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.main import app as production_app
from backend.app.offline_registration_certification_routes import (
    router as offline_router,
)
from backend.app.loanhub_staff_verifier import LoanHubStaffVerifier
from backend.app.staff_authorization import VerifiedStaffIdentity
from backend.app.staff_login_routes import (
    COOKIE, CSRF_COOKIE, StaffLoginConfig, StagingStaffSessionStore,
)

ORIGIN = "https://batlokoa-cert.example"
UPSTREAM = "https://loanhub-offline.example"
COMPANY, EMPLOYEE, BRANCH, OTHER_BRANCH, ACCOUNT = (
    uuid4() for _ in range(5)
)
PATH = "/api/v1/staff/clients/register"
KEY = "synthetic-save-request-0001"


def full_capture():
    return {
        "branch_id": str(BRANCH),
        "first_name": "Palesa",
        "middle_name": "Synthetic",
        "last_name": "Mokoena",
        "phone": "59000001",
        "national_id": "SYNTHETIC-NOT-REAL",
        "date_of_birth": "1991-05-01",
        "gender": "female",
        "district": "Maseru",
        "employment_status": "employed",
        "employer_name": "Synthetic employer",
        "monthly_income": "6000.00",
        "has_existing_loans": True,
        "existing_loan_total": "500.00",
        "external_debts": [{
            "creditor": "Synthetic bank",
            "current_balance": "500.00",
            "installment_amount": "100.00",
            "remaining_installments": 5,
        }],
        "bank_account": {
            "bank_name": "FNB",
            "account_holder": "Palesa Mokoena",
            "account_number": "61234567890",
            "salary_account": True,
        },
        "consent_to_share_profile": True,
        "consent_to_credit_checks": True,
    }


def setup(monkeypatch, *, upstream_status=201, response_body=None,
          role="LOAN_OFFICER", branch_ids=None):
    monkeypatch.setenv(
        "BATLOKOA_OFFLINE_REGISTRATION_ACK", "disposable_sandbox_only",
    )
    outgoing = []
    receipt = response_body if response_body is not None else {
        "registered": True, "client_account_id": str(ACCOUNT),
        "replayed": False,
    }

    def handler(request):
        outgoing.append(request)
        return httpx.Response(upstream_status, json=receipt)

    upstream_client = httpx.Client(transport=httpx.MockTransport(handler))
    verifier = LoanHubStaffVerifier(
        origin=UPSTREAM, public_key="synthetic-test-key",
        batlokoa_company_id=COMPANY,
    )
    identity = VerifiedStaffIdentity(
        user_id=EMPLOYEE, company_id=COMPANY, role=role, active=True,
        branch_ids=frozenset({BRANCH} if branch_ids is None else branch_ids),
    )

    def verify(self, token):
        assert token == "synthetic-access"
        return identity

    verifier.verify = MethodType(verify, verifier)
    store = StagingStaffSessionStore()
    session_id, csrf = store.issue("synthetic-access", 300)
    app = FastAPI()
    app.include_router(offline_router)
    app.state.staff_login_config = StaffLoginConfig(
        ORIGIN, UPSTREAM, verifier, store, client=upstream_client,
    )
    client = TestClient(app, base_url=ORIGIN)
    client.cookies.set(COOKIE, session_id)
    client.cookies.set(CSRF_COOKIE, csrf)
    return client, outgoing, csrf


def submit(client, csrf, *, body=None, origin=ORIGIN, key=KEY):
    return client.post(
        PATH, json=full_capture() if body is None else body,
        headers={
            "Origin": origin,
            "X-CSRF-Token": csrf,
            "Idempotency-Key": key,
        },
    )


def test_offline_post_absent_from_real_app():
    assert all(
        getattr(route, "path", None) != PATH
        for route in production_app.routes
    )


def test_full_payload_passes_unchanged_with_verified_staff_scope(monkeypatch):
    client, outgoing, csrf = setup(monkeypatch)
    result = submit(client, csrf)
    assert result.status_code == 201
    assert result.json() == {
        "registered": True, "client_account_id": str(ACCOUNT),
        "replayed": False,
    }
    assert result.headers["cache-control"] == "no-store"
    assert len(outgoing) == 1
    request = outgoing[0]
    assert request.method == "POST"
    assert str(request.url) == UPSTREAM + "/api/v1/batlokoa/registration/clients"
    assert request.headers["authorization"] == "Bearer synthetic-access"
    assert request.headers["x-company-id"] == str(COMPANY)
    assert request.headers["x-active-role"] == "loan_officer"
    assert request.headers["idempotency-key"] == KEY
    assert json.loads(request.content) == full_capture()
    assert "SYNTHETIC-NOT-REAL" not in result.text
    assert "61234567890" not in result.text


def test_offline_ack_missing_blocks_any_upstream_call(monkeypatch):
    client, outgoing, csrf = setup(monkeypatch)
    monkeypatch.delenv("BATLOKOA_OFFLINE_REGISTRATION_ACK")
    result = submit(client, csrf)
    assert result.status_code == 503
    assert outgoing == []


def test_foreign_origin_and_wrong_csrf_do_not_call_loanhub(monkeypatch):
    client, outgoing, csrf = setup(monkeypatch)
    assert submit(client, csrf, origin="https://attacker.example").status_code == 403
    assert submit(client, "wrong-csrf").status_code == 403
    client.cookies.delete(COOKIE)
    assert submit(client, csrf).status_code == 401
    assert outgoing == []


def test_wrong_branch_or_non_lending_role_cannot_write(monkeypatch):
    client, outgoing, csrf = setup(monkeypatch)
    bad = {**full_capture(), "branch_id": str(OTHER_BRANCH)}
    assert submit(client, csrf, body=bad).status_code == 403
    assert outgoing == []
    client2, outgoing2, csrf2 = setup(monkeypatch, role="AUDITOR")
    assert submit(client2, csrf2).status_code == 403
    assert outgoing2 == []


@pytest.mark.parametrize("unsafe", [
    {"company_id": "spoof"},
    {"user_id": "spoof"},
    {"independently_approved_release": True},
    {"registered": True},
])
def test_browser_cannot_claim_tenant_or_release(monkeypatch, unsafe):
    client, outgoing, csrf = setup(monkeypatch)
    result = submit(client, csrf, body={**full_capture(), **unsafe})
    assert result.status_code == 422
    assert outgoing == []


def test_invalid_request_and_key_do_not_call_upstream(monkeypatch):
    client, outgoing, csrf = setup(monkeypatch)
    assert submit(client, csrf, key="short").status_code == 422
    assert submit(client, csrf, body={"first_name": "Synthetic"}).status_code == 422
    assert outgoing == []


@pytest.mark.parametrize("upstream_status,expected", [
    (200, 503), (202, 503), (302, 503),
    (401, 403), (403, 403), (409, 409),
    (422, 422), (500, 503), (503, 503),
])
def test_non_201_upstream_cannot_confirm_registration(
    monkeypatch, upstream_status, expected,
):
    client, outgoing, csrf = setup(
        monkeypatch, upstream_status=upstream_status,
        response_body={
            "registered": True, "client_account_id": str(ACCOUNT),
            "replayed": False, "borrower_phone": "59000001",
        },
    )
    result = submit(client, csrf)
    assert result.status_code == expected
    assert "registered" not in result.json()
    assert "59000001" not in result.text
    assert len(outgoing) == 1


@pytest.mark.parametrize("receipt", [
    {"registered": False, "client_account_id": str(ACCOUNT), "replayed": False},
    {"registered": True, "client_account_id": "not-a-uuid", "replayed": False},
    {"registered": True, "client_account_id": str(ACCOUNT), "replayed": "false"},
    {"registered": True, "client_account_id": str(ACCOUNT), "replayed": False, "pii": "secret"},
    {"registered": True, "client_account_id": None, "replayed": False},
])
def test_untrusted_201_confirmation_never_claims_saved(monkeypatch, receipt):
    client, outgoing, csrf = setup(monkeypatch, response_body=receipt)
    response = submit(client, csrf)
    assert response.status_code == 503
    assert response.json() == {"code": "UNTRUSTED_REGISTRATION_RECEIPT"}
    assert len(outgoing) == 1


def test_explicit_replay_keeps_same_idempotency_key(monkeypatch):
    client, outgoing, csrf = setup(monkeypatch, response_body={
        "registered": True, "client_account_id": str(ACCOUNT),
        "replayed": True,
    })
    response = submit(client, csrf)
    assert response.status_code == 201
    assert response.json() == {
        "registered": True, "client_account_id": str(ACCOUNT),
        "replayed": True,
    }
    assert len(outgoing) == 1
    assert outgoing[0].headers["idempotency-key"] == KEY


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_uncertain_responses_never_claim_client_saved(monkeypatch, status):
    client, outgoing, csrf = setup(monkeypatch, upstream_status=status)
    first = submit(client, csrf)
    second = submit(client, csrf)
    assert first.status_code == 503
    assert second.status_code == 503
    assert "registered" not in first.json()
    assert "registered" not in second.json()
    assert len(outgoing) == 2
    assert all(req.headers["idempotency-key"] == KEY for req in outgoing)


def test_expired_or_revoked_staff_session_cannot_forward(monkeypatch):
    client, outgoing, csrf = setup(monkeypatch)
    cfg = client.app.state.staff_login_config
    # A revoked session must be rejected independently of its CSRF cookie.
    session_id = client.cookies.get(COOKIE)
    cfg.store.revoke(session_id)
    response = submit(client, csrf)
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"
    assert outgoing == []


def test_expired_access_token_cannot_forward(monkeypatch):
    from backend.app.loanhub_staff_verifier import StaffVerificationUnavailable

    client, outgoing, csrf = setup(monkeypatch)
    cfg = client.app.state.staff_login_config

    def unavailable(_):
        raise StaffVerificationUnavailable("Expired synthetic staff token")

    cfg.verifier.verify = unavailable
    response = submit(client, csrf)
    assert response.status_code == 401
    assert outgoing == []
    assert client.cookies.get(COOKIE) is not None


@pytest.mark.parametrize("transport_exc", [
    httpx.ReadTimeout("simulated timeout"),
    httpx.ConnectError("simulated disconnect"),
    httpx.RemoteProtocolError("simulated lost response"),
])
def test_transport_failure_must_not_claim_client_saved(monkeypatch, transport_exc):
    client, outgoing, csrf = setup(monkeypatch)

    def broken(_):
        raise transport_exc

    cfg = client.app.state.staff_login_config
    cfg.client = httpx.Client(transport=httpx.MockTransport(broken))
    result = submit(client, csrf)
    assert result.status_code == 503
    assert result.json() == {"code": "REGISTRATION_UNAVAILABLE"}
    assert "registered" not in result.json()
    assert outgoing == []


def test_replay_after_ambiguous_upstream_result_uses_same_request_key(monkeypatch):
    client, outgoing, csrf = setup(monkeypatch)
    calls = []

    def intermittent(request):
        calls.append(request)
        if len(calls) == 1:
            # LoanHub may have committed before its response was lost.
            raise httpx.ReadTimeout("response lost after commit")
        return httpx.Response(201, json={
            "registered": True,
            "client_account_id": str(ACCOUNT),
            "replayed": True,
        })

    cfg = client.app.state.staff_login_config
    cfg.client = httpx.Client(transport=httpx.MockTransport(intermittent))
    uncertain = submit(client, csrf)
    assert uncertain.status_code == 503
    assert "registered" not in uncertain.json()
    replay = submit(client, csrf)
    assert replay.status_code == 201
    assert replay.json() == {
        "registered": True, "client_account_id": str(ACCOUNT),
        "replayed": True,
    }
    assert len(calls) == 2
    assert all(req.headers["idempotency-key"] == KEY for req in calls)
    assert all(json.loads(req.content) == full_capture() for req in calls)


def test_missing_or_malformed_content_type_never_confirms(monkeypatch):
    client, outgoing, csrf = setup(monkeypatch)
    config = client.app.state.staff_login_config

    for response in (
        httpx.Response(201, content=b"ok", headers={
            "content-type": "text/plain",
        }),
        httpx.Response(201, content=b"{invalid", headers={
            "content-type": "application/json",
        }),
        httpx.Response(201, json={
            "registered": True, "client_account_id": str(ACCOUNT),
            "replayed": False, "secret": "x" * 5000,
        }),
    ):
        def handler(_):
            return response

        config.client = httpx.Client(transport=httpx.MockTransport(handler))
        result = submit(client, csrf)
        assert result.status_code == 503
        assert "registered" not in result.json()
        assert str(ACCOUNT) not in result.text


def test_oversized_request_rejected_without_upstream_call(monkeypatch):
    client, outgoing, csrf = setup(monkeypatch)
    oversized = {**full_capture(), "physical_address": "x" * 33000}
    response = submit(client, csrf, body=oversized)
    assert response.status_code == 413
    assert response.json() == {"code": "REGISTRATION_TOO_LARGE"}
    assert outgoing == []


def test_malformed_client_branch_type_rejected_before_upstream(monkeypatch):
    client, outgoing, csrf = setup(monkeypatch)
    for bad in (None, 5, False, [], {}):
        result = submit(client, csrf, body={
            **full_capture(), "branch_id": bad,
        })
        assert result.status_code == 422
    assert outgoing == []


def test_duplicate_top_level_and_nested_json_keys_are_rejected(monkeypatch):
    client, outgoing, csrf = setup(monkeypatch)
    body = json.dumps(full_capture())
    # Duplicate fields can otherwise be silently overwritten by json.loads.
    duplicate_branch = body[:-1] + ',"branch_id":"' + str(OTHER_BRANCH) + '"}'
    duplicate_nested = body.replace(
        '"account_number": "61234567890"',
        '"account_number": "61234567890", "account_number": "999999999"',
    )
    for raw in (duplicate_branch, duplicate_nested):
        response = client.post(
            PATH, content=raw,
            headers={
                "Origin": ORIGIN, "X-CSRF-Token": csrf,
                "Idempotency-Key": KEY,
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 422
        assert response.json() == {"code": "INVALID_REGISTRATION"}
    assert outgoing == []


def test_nan_and_infinity_are_rejected_before_forwarding(monkeypatch):
    client, outgoing, csrf = setup(monkeypatch)
    raw = json.dumps(full_capture())[:-1] + ',"monthly_income":NaN}'
    response = client.post(
        PATH, content=raw, headers={
            "Origin": ORIGIN, "X-CSRF-Token": csrf,
            "Idempotency-Key": KEY,
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 422
    assert outgoing == []
