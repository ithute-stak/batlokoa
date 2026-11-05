"""Phase 49: encrypted, bounded, deliberately nonproduction token staging."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from backend.app.loanhub_grant_broker import (
    BorrowerAccountEvidence, LoanHubBorrowerGrantBroker,
)
from backend.app.staging_borrower_vault import EphemeralBorrowerTokenVault

TENANT = "d921126e-e1a7-482e-ad1b-6e99b1682e19"
OTHER_TENANT = "9ff995dc-ad87-4a91-8a8f-18ddfc85d991"
BORROWER = "cb6700f8-1808-46ca-bfc2-f030ad0e2d7c"
OTHER_BORROWER = "9ff995dc-ad87-4a91-8a8f-18ddfc85d992"
TOKEN = "synthetic-loanhub-borrower-credential"


def fixture_vault(*, max_entries=4, max_ttl=timedelta(minutes=5)):
    state = {"valid": True, "calls": 0, "role": "borrower"}
    def verify(token, tenant, borrower):
        state["calls"] += 1
        if not state["valid"] or token != TOKEN:
            return None
        now = datetime.now(timezone.utc)
        return BorrowerAccountEvidence(
            tenant_id=tenant,
            borrower_id=borrower,
            role=state["role"],
            account_active=True,
            session_active=True,
            verified_at=now,
            token_expires_at=now + timedelta(minutes=2),
        )
    vault = EphemeralBorrowerTokenVault(
        encryption_key=Fernet.generate_key(),
        verify_token_for=verify,
        max_entries=max_entries,
        max_ttl=max_ttl,
    )
    return vault, state, verify


def test_requires_explicit_valid_key_and_bounded_capacity():
    with pytest.raises(ValueError):
        EphemeralBorrowerTokenVault(
            encryption_key=b"placeholder", verify_token_for=lambda *args: None
        )
    for bad in (0, 257, True):
        with pytest.raises(ValueError):
            EphemeralBorrowerTokenVault(
                encryption_key=Fernet.generate_key(),
                verify_token_for=lambda *args: None, max_entries=bad,
            )


def test_provisions_only_verified_exact_tenant_borrower():
    vault, state, verifier = fixture_vault()
    sid = uuid4()
    assert vault.provision(tenant_id=TENANT, borrower_id=BORROWER, central_sid=sid, token=TOKEN)
    assert vault.token_for(TENANT, BORROWER) == TOKEN
    assert vault.token_for(OTHER_TENANT, BORROWER) is None
    assert vault.token_for(TENANT, OTHER_BORROWER) is None
    assert state["calls"] == 1
    vault.close()
    assert vault.token_for(TENANT, BORROWER) is None


def test_stored_payload_is_ciphertext_not_plaintext():
    vault, _, _ = fixture_vault()
    assert vault.provision(
        tenant_id=TENANT, borrower_id=BORROWER,
        central_sid=uuid4(), token=TOKEN,
    )
    entry = vault._entries[(TENANT, BORROWER)]
    assert TOKEN.encode() not in entry.ciphertext
    assert vault._cipher.decrypt(entry.ciphertext) == TOKEN.encode()


@pytest.mark.parametrize("token", ["", " ", "secret token", "a\n", "é", "x" * 8193])
def test_rejects_invalid_input_before_storage(token):
    vault, state, _ = fixture_vault()
    assert not vault.provision(
        tenant_id=TENANT, borrower_id=BORROWER,
        central_sid=uuid4(), token=token,
    )
    assert vault.token_for(TENANT, BORROWER) is None
    assert state["calls"] == 0


def test_invalid_identity_or_permission_does_not_insert():
    vault, state, _ = fixture_vault()
    state["role"] = "superadmin"
    assert not vault.provision(
        tenant_id=TENANT, borrower_id=BORROWER, central_sid=uuid4(), token=TOKEN,
    )
    state["role"] = "borrower"
    state["valid"] = False
    assert not vault.provision(
        tenant_id=TENANT, borrower_id=BORROWER, central_sid=uuid4(), token=TOKEN,
    )
    assert vault.token_for(TENANT, BORROWER) is None


def test_session_revocation_erases_and_blocks_reprovisioning():
    vault, state, _ = fixture_vault()
    sid = uuid4()
    assert vault.provision(
        tenant_id=TENANT, borrower_id=BORROWER, central_sid=sid, token=TOKEN,
    )
    assert vault.revoke_central_session(sid) == 1
    assert vault.token_for(TENANT, BORROWER) is None
    assert not vault.provision(
        tenant_id=TENANT, borrower_id=BORROWER, central_sid=sid, token=TOKEN,
    )
    assert vault.revoke_central_session(sid) == 0
    assert vault.provision(
        tenant_id=TENANT, borrower_id=BORROWER,
        central_sid=uuid4(), token=TOKEN,
    )


def test_existing_borrower_grant_cannot_be_overwritten_by_other_session():
    vault, state, _ = fixture_vault()
    first = uuid4()
    assert vault.provision(
        tenant_id=TENANT, borrower_id=BORROWER,
        central_sid=first, token=TOKEN,
    )
    assert not vault.provision(
        tenant_id=TENANT, borrower_id=BORROWER,
        central_sid=uuid4(), token=TOKEN,
    )
    assert vault.token_for(TENANT, BORROWER) == TOKEN


def test_capacity_bound_and_expiry_are_fail_closed():
    vault, state, _ = fixture_vault(max_entries=1, max_ttl=timedelta(seconds=10))
    assert vault.provision(
        tenant_id=TENANT, borrower_id=BORROWER,
        central_sid=uuid4(), token=TOKEN,
    )
    assert not vault.provision(
        tenant_id=OTHER_TENANT, borrower_id=OTHER_BORROWER,
        central_sid=uuid4(), token=TOKEN,
    )
    from dataclasses import replace
    original = vault._entries[(TENANT, BORROWER)]
    vault._entries[(TENANT, BORROWER)] = replace(
        original, expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    assert vault.token_for(TENANT, BORROWER) is None
    assert vault.provision(
        tenant_id=OTHER_TENANT, borrower_id=OTHER_BORROWER,
        central_sid=uuid4(), token=TOKEN,
    )


def test_revocation_also_enforced_by_broker_on_each_read():
    vault, state, verifier = fixture_vault()
    sid = uuid4()
    assert vault.provision(
        tenant_id=TENANT, borrower_id=BORROWER,
        central_sid=sid, token=TOKEN,
    )
    broker = LoanHubBorrowerGrantBroker(
        token_for=vault.token_for, verify_token_for=verifier,
    )
    grant = broker(TENANT, BORROWER)
    assert grant is not None and grant.token == TOKEN
    state["valid"] = False
    assert broker(TENANT, BORROWER) is None
    state["valid"] = True
    assert vault.revoke_borrower(TENANT, BORROWER)
    assert broker(TENANT, BORROWER) is None
