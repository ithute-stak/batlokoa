# Phase 48 — LoanHub-to-Batlokoa end-to-end authorization certification

The test `backend/tests/test_phase48_remote_loanhub_end_to_end.py` uses
synthetic RS256 LoanHub borrower credentials and an in-memory HTTP transport
to exercise the **real Batlokoa** sequence:

1. Obtain an already-approved borrower token from a synthetic backend vault.
2. Cryptographically verify the token and query LoanHub `/auth/me`.
3. Call LoanHub `/auth/borrower-context?company_id=...` using the same
   borrower token and verify the user, tenant, borrower and session state.
4. Only then release a short-lived authorization grant to the read-only
   `GET /api/v1/loans/` adapter.
5. Refuse results for any other company or borrower, malformed amount,
   expired token, mismatched role, revoked token or unavailable service.

The test checks that a successful loan read is **not cached** across
revocation or mapping changes. Failure during verification must stop
**before** any call to LoanHub's loans endpoint.

This is **not** a production borrower acceptance test. It does not create
or access a real borrower account or LoanHub database. It does not deploy
new images, set OIDC registration credentials, enable Batlokoa loan reads
or enable IthutePay. The publicly accessible Batlokoa gateway must
continue to advertise `integration_disabled` and return 503 from
customer-data and payment routes.

## Still required for customer activation

- Controlled test account with consent and an approved LoanHub company
  association; verify actual login, logout, session revocation, MFA policy
  and access after password reset on the *running* LoanHub API.
- Review and provision a trusted server-side token vault and authentication
  policy; never pass browser-supplied LoanHub roles, tenant IDs or admin tokens.
- Approve data processing and access auditing for the institution.
- Perform isolated staging deployment and negative cross-company tests.
- Keep payments separately disabled until IthutePay merchant authorization,
  reconciliation and incident response are signed off.
