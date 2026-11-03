"""Contract tests; no production customer account is linked."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from backend.app.account_linking import (
    AccountLinkService, DisabledLinkStore, LinkConflict, LinkConsent,
    LinkDenied, LinkUnavailable, LoanHubBorrowerProof,
)
from backend.app.identity import CustomerContext, VerifiedClaims

TENANT = UUID("d921126e-e1a7-482e-ad1b-6e99b1682e19")
BORROWER = UUID("cb6700f8-1808-46ca-bfc2-f030ad0e2d7c")
ISSUER = "https://auth.example.test"
NOW = datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc)


class Verifier:
    def __init__(self, result=True):
        self.result = result
        self.calls = []

    async def is_active_tenant_borrower(self, *, tenant_id, borrower_id):
        self.calls.append((tenant_id, borrower_id))
        return self.result


class MemoryStore:
    """Only for unit tests: mimics atomic uniqueness in sequential requests."""
    def __init__(self):
        self.by_subject = {}
        self.by_borrower = {}
        self.proofs = set()

    async def bind_once(self, *, issuer, subject, tenant_id, borrower_id,
                        consent_reference, proof_id):
        subject_key = (issuer, subject, tenant_id)
        borrower_key = (tenant_id, borrower_id)
        if (subject_key in self.by_subject or borrower_key in self.by_borrower
                or proof_id in self.proofs):
            raise LinkConflict("Already linked")
        result = CustomerContext(
            tenant_id=str(tenant_id), customer_id=str(borrower_id),
            auth_subject=subject)
        self.by_subject[subject_key] = result
        self.by_borrower[borrower_key] = result
        self.proofs.add(proof_id)
        return result


def material():
    claims = VerifiedClaims(
        sub="central-sub-1", iss=ISSUER, aud="batlokoa-gateway",
        iat=1800000000, exp=2000000000,
    )
    proof = LoanHubBorrowerProof(
        borrower_id=BORROWER, central_auth_subject=claims.sub,
        role="BORROWER", authenticated_at=NOW - timedelta(seconds=10),
        proof_id="proof-session-123",
    )
    consent = LinkConsent(
        subject=claims.sub, tenant_id=TENANT, borrower_id=BORROWER,
        acknowledged_at=NOW - timedelta(seconds=8),
        consent_reference="consent-session-456",
    )
    return claims, proof, consent


def service(*, verifier=None, store=None):
    return AccountLinkService(
        tenant_id=TENANT, issuer=ISSUER,
        verifier=verifier or Verifier(), store=store or MemoryStore())


@pytest.mark.asyncio
async def test_requires_two_verified_matching_identities_and_consent():
    claims, proof, consent = material()
    verifier, store = Verifier(), MemoryStore()
    result = await service(verifier=verifier, store=store).link(
        claims=claims, borrower=proof, consent=consent, now=NOW)
    assert result.tenant_id == str(TENANT)
    assert result.customer_id == str(BORROWER)
    assert verifier.calls == [(TENANT, BORROWER)]
    assert store.by_subject[(ISSUER, claims.sub, TENANT)] == result


@pytest.mark.asyncio
@pytest.mark.parametrize("mutate", [
    lambda c,p,t: (c, replace(p, role="COMPANY_ADMIN"), t),
    lambda c,p,t: (c, replace(p, central_auth_subject="someone-else"), t),
    lambda c,p,t: (c, p, replace(t, subject="someone-else")),
    lambda c,p,t: (c, p, replace(t, tenant_id=UUID("9ff995dc-ad87-4a91-8a8f-18ddfc85d991"))),
    lambda c,p,t: (c, p, replace(t, borrower_id=UUID("9ff995dc-ad87-4a91-8a8f-18ddfc85d991"))),
    lambda c,p,t: (c, replace(p, authenticated_at=NOW-timedelta(minutes=10)), t),
    lambda c,p,t: (c, p, replace(t, acknowledged_at=NOW-timedelta(minutes=10))),
    lambda c,p,t: (c, replace(p, proof_id=""), t),
    lambda c,p,t: (c, p, replace(t, consent_reference="")),
])
async def test_untrusted_or_expired_link_evidence_is_denied(mutate):
    claims, proof, consent = mutate(*material())
    verifier, store = Verifier(), MemoryStore()
    with pytest.raises(LinkDenied):
        await service(verifier=verifier, store=store).link(
            claims=claims, borrower=proof, consent=consent, now=NOW)
    assert verifier.calls == []
    assert store.by_subject == {}


@pytest.mark.asyncio
async def test_cross_tenant_borrower_rejected_before_persistence():
    claims, proof, consent = material()
    verifier, store = Verifier(False), MemoryStore()
    with pytest.raises(LinkDenied):
        await service(verifier=verifier, store=store).link(
            claims=claims, borrower=proof, consent=consent, now=NOW)
    assert store.by_subject == {}


@pytest.mark.asyncio
async def test_store_rejects_replay_and_conflicting_subjects():
    claims, proof, consent = material()
    store = MemoryStore()
    linker = service(store=store)
    await linker.link(claims=claims, borrower=proof, consent=consent, now=NOW)
    with pytest.raises(LinkConflict):
        await linker.link(claims=claims, borrower=proof, consent=consent, now=NOW)
    another = claims.model_copy(update={"sub": "different-central-sub"})
    other_proof = replace(proof, central_auth_subject="different-central-sub",
                          proof_id="different-proof-789")
    other_consent = replace(consent, subject="different-central-sub",
                            consent_reference="different-consent-789")
    with pytest.raises(LinkConflict):
        await linker.link(claims=another, borrower=other_proof,
                          consent=other_consent, now=NOW)


@pytest.mark.asyncio
async def test_default_store_never_creates_a_live_customer_link():
    claims, proof, consent = material()
    linker = service(store=DisabledLinkStore())
    with pytest.raises(LinkUnavailable):
        await linker.link(claims=claims, borrower=proof, consent=consent, now=NOW)


@pytest.mark.asyncio
async def test_issuer_mismatch_is_denied():
    claims, proof, consent = material()
    with pytest.raises(LinkDenied):
        await service().link(claims=claims.model_copy(update={"iss": "https://other.example.test"}),
                             borrower=proof, consent=consent, now=NOW)
