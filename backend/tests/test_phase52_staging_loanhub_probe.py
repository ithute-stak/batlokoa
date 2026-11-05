"""Phase 52: mock HTTP regression for explicit read-only staging probe."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.app.staging_loanhub_probe import (
    ProbeOutcome, probe_approved_staging_borrower,
)

ORIGIN = "https://approved-staging.invalid"
COMPANY = "d921126e-e1a7-482e-ad1b-6e99b1682e19"
BORROWER = "cb6700f8-1808-46ca-bfc2-f030ad0e2d7c"
USER = "72de5a5b-ad44-4eea-b871-81479fe7b045"


@pytest.mark.asyncio
async def test_explicit_approved_borrower_read_only_probe():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = jwt.encode({
        "user_id": USER, "token_type": "access",
        "session_jti": str(uuid4()), "session_version": 1,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }, key, algorithm="RS256")
    calls = []
    state = {"revoked": False, "wrong_company": False}

    def respond(request: httpx.Request):
        calls.append((request.method, request.url.path))
        assert request.method == "GET"
        assert request.url.scheme == "https"
        assert request.headers.get("authorization") == f"Bearer {token}"
        assert request.headers["cache-control"] == "no-store"
        if state["revoked"]:
            return httpx.Response(401)
        if request.url.path == "/api/v1/auth/me":
            return httpx.Response(200, json={
                "id": USER, "role": "borrower",
                "is_active": True, "is_verified": True,
                "must_change_password": False,
            })
        if request.url.path == "/api/v1/auth/borrower-context":
            return httpx.Response(200, json={
                "user_id": USER,
                "company_id": str(uuid4()) if state["wrong_company"] else COMPANY,
                "borrower_id": BORROWER,
                "role": "borrower",
                "session_active": True,
                "account_active": True,
            })
        if request.url.path == "/api/v1/loans/":
            return httpx.Response(200, json=[{
                "id": str(uuid4()), "company_id": COMPANY,
                "borrower_id": BORROWER,
                "balance": "13.00", "status": "active",
            }])
        raise AssertionError("unexpected endpoint")

    transport = httpx.MockTransport(respond)
    with httpx.Client(transport=transport) as sync:
        async with httpx.AsyncClient(transport=transport) as asynchronous:
            args = dict(
                loanhub_origin=ORIGIN, approved_origin=ORIGIN,
                company_id=COMPANY, borrower_id=BORROWER,
                borrower_access_token=token, trusted_public_key=key.public_key(),
                approved_staging=True, client=sync, async_client=asynchronous,
            )
            result = await probe_approved_staging_borrower(**args)
            assert result.outcome == ProbeOutcome.VERIFIED_READ_ONLY
            assert not result.customer_access_enabled and not result.payments_enabled
            assert calls == [
                ("GET", "/api/v1/auth/me"),
                ("GET", "/api/v1/auth/borrower-context"),
                ("GET", "/api/v1/auth/me"),
                ("GET", "/api/v1/auth/borrower-context"),
                ("GET", "/api/v1/loans/"),
            ]
            calls.clear()
            state["revoked"] = True
            result = await probe_approved_staging_borrower(**args)
            assert result.outcome == ProbeOutcome.AUTHORIZATION_DENIED
            assert all(path != "/api/v1/loans/" for _, path in calls)
            calls.clear()
            state["revoked"] = False
            state["wrong_company"] = True
            result = await probe_approved_staging_borrower(**args)
            assert result.outcome == ProbeOutcome.AUTHORIZATION_DENIED
            assert all(path != "/api/v1/loans/" for _, path in calls)


@pytest.mark.asyncio
async def test_unapproved_scope_never_calls_network():
    def forbidden(_request):
        raise AssertionError("unapproved scope must not connect")
    with httpx.Client(transport=httpx.MockTransport(forbidden)) as sync:
        async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as asynchronous:
            result = await probe_approved_staging_borrower(
                loanhub_origin=ORIGIN, approved_origin="https://different.invalid",
                company_id=COMPANY, borrower_id=BORROWER,
                borrower_access_token="no", trusted_public_key=object(),
                approved_staging=True, client=sync, async_client=asynchronous,
            )
            assert result.outcome == ProbeOutcome.INVALID_STAGING_SCOPE
