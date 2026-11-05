# Phase 51 — Unified staging-readiness decision

This phase combines the Phase 49 credential-mount metadata checker and the
Phase 50 acceptance-evidence checker in
`backend/app/staging_readiness_gate.py`.

A positive result requires both validators to pass and the reviewed metadata
to match the **same** approved LoanHub company, test borrower, approval reference
and approval expiry. A mismatched identity or approval fails closed.

The result is named `ready_for_manual_security_review`, not
`staging_accepted` or `production_ready`. This module cannot attest to the
authenticity of operator-provided evidence, inspect actual token signatures,
run LoanHub calls, inspect the live environment, or provision any credentials.

## Remaining mandatory activities

1. Obtain authorization for a non-customer staging borrower and set up a
   separate private staging runtime with restricted outbound connectivity.
2. Independently inspect the issuer, token signature, signing-key provenance,
   environment configuration and approval evidence.
3. Carry out actual login, read-only loan retrieval, cross-company denial,
   logout, revocation, session version and outage tests with redacted records.
4. Independently verify operator evidence and ensure the staging setup cannot
   access production customer data or enable payments.
5. Repeat required checks after code or infrastructure changes, and obtain
   explicit second-party approval before any activation.

Nothing in this phase deploys a container, updates VPS secrets or modifies
public Batlokoa settings. Public `integration_disabled` remains the expected
operational response. IthutePay remains disabled.
