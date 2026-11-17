"""Synthetic LoanHub staff authorization tests; no external network."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.app.loanhub_staff_verifier import LoanHubStaffVerifier, StaffVerificationUnavailable
from backend.app.staff_authorization import StaffPermission, require_staff_permission

COMPANY, OTHER, BRANCH, USER = (uuid4() for _ in range(4))
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC = KEY.public_key()


def token(**changes):
    claims = dict(user_id=str(USER), token_type="access",
                  session_jti="real-session-id",
                  exp=datetime.now(timezone.utc) + timedelta(minutes=5))
    claims.update(changes)
    return jwt.encode(claims, KEY, algorithm="RS256")


def response(**changes):
    payload = dict(
        id=str(USER), role="loan_officer", is_active=True,
        is_verified=True, must_change_password=False,
        memberships=[dict(company_id=str(COMPANY), branch_id=str(BRANCH),
                          is_active=True, role="loan_officer")],
    )
    payload.update(changes)
    return httpx.Response(200, json=payload)


def verify(res, *, token_value=None, status=None):
    calls = []
    def handler(req):
        calls.append(req)
        return res
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        service = LoanHubStaffVerifier(origin="https://staging.loanhub.example",
                                       public_key=PUBLIC,
                                       batlokoa_company_id=COMPANY,
                                       client=client)
        try:
            identity = service.verify(token_value or token())
            if status == "deny":
                pytest.fail("Expected staff verification denial")
            return identity, calls
        except StaffVerificationUnavailable:
            if status != "deny":
                raise
            return None, calls


def test_active_employee_resolves_branch_and_permissions():
    identity, calls = verify(response())
    assert identity.user_id == USER
    assert identity.branch_ids == frozenset({BRANCH})
    assert not identity.company_wide_scope
    require_staff_permission(identity, expected_company_id=COMPANY,
                             branch_id=BRANCH,
                             permission=StaffPermission.REGISTER_CLIENT)
    assert len(calls) == 1
    assert calls[0].url.path == "/api/v1/auth/me"


@pytest.mark.parametrize("bad", [
    response(is_active=False),
    response(is_verified=False),
    response(must_change_password=True),
    response(role="borrower"),
    response(memberships=[]),
    response(memberships=[dict(company_id=str(OTHER), branch_id=str(BRANCH),
                               is_active=True, role="loan_officer")]),
    response(memberships=[dict(company_id=str(COMPANY), branch_id=None,
                               is_active=True, role="loan_officer")]),
    response(memberships=[dict(company_id=str(COMPANY), branch_id=str(BRANCH),
                               is_active=False, role="loan_officer")]),
    response(memberships=[dict(company_id=str(COMPANY), branch_id=str(BRANCH),
                               is_active=True, role="cashier")]),
    httpx.Response(503, json={"error": "unavailable"}),
    httpx.Response(302, headers={"Location": "https://other.example"}),
])
def test_fail_closed_for_invalid_accounts_memberships_and_upstream(bad):
    verify(bad, status="deny")


def test_rejects_impersonation_without_network():
    _, calls = verify(response(), token_value=token(impersonated_by=str(uuid4())),
                      status="deny")
    assert calls == []


def test_rejects_wrong_signing_key_without_network():
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(dict(user_id=str(USER), token_type="access",
                             session_jti="x",
                             exp=datetime.now(timezone.utc) + timedelta(minutes=5)),
                        other_key, algorithm="RS256")
    _, calls = verify(response(), token_value=forged, status="deny")
    assert calls == []


def test_company_admin_can_resolve_company_scope():
    admin = response(memberships=[dict(company_id=str(COMPANY),
                                       branch_id=None, is_active=True,
                                       role="company_admin")])
    identity, _ = verify(admin)
    assert identity.company_wide_scope is True
