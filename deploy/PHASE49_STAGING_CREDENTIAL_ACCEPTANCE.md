# Phase 49 — staging credential provisioning and acceptance boundary

This phase adds a **metadata-only** staging preflight in
`backend/app/staging_credential_provisioning.py` and network-free tests in
`backend/tests/test_phase49_staging_credential_provisioning.py`.

The preflight checks: canonical tenant/test-borrower UUIDs; an HTTPS LoanHub
origin; regular, owner-controlled secret/public-key files with no group or
world permissions; a current staging approval reference; and disabled payment
and live-customer feature flags. It **does not read or log secret bytes**,
make a LoanHub request, provision an account, install a credential, enable
routes, or certify the public demonstration.

## Operator-run acceptance (not yet executed)

1. Obtain written authorization for a **non-customer** test borrower and
   verify its company ownership with LoanHub administrators.
2. Issue a short-lived, least-privilege borrower token using the approved
   LoanHub login process. Never use an admin token or commit any token,
   password or private key to Git, CI logs or Docker image layers.
3. Mount the token and trusted LoanHub **public** verification key
   as independent read-only files in a private staging runtime. The
   runtime user must have access; deny group/world access. Mount paths
   belong in deployment-specific secret configuration, not in the web UI.
4. Run the offline Phase 49 tests. Have an operator review the preflight
   metadata and verify the **actual token signature and claims** independently.
   Passing preflight is **not** evidence of token validity.
5. In isolated staging only, exercise LoanHub `/api/v1/auth/me` and
   `/api/v1/auth/borrower-context` for the approved account; confirm the
   matching borrower/company before a read-only `/api/v1/loans/` call.
6. Repeat after logout, revocation and password/session-version changes;
   deny different-company borrower access, expired credentials, and outages.
   Record redacted statuses, not personal data or bearer tokens.
7. Require a second-party security review before any customer-data
   activation. Keep payment initiation, repayment, wallets, merchant
   activation and IthutePay settlement separately disabled.

## Explicit limits

No staging or production deployment has been performed by this change.
No real LoanHub borrower login or live revocation test is claimed.
Public Batlokoa capabilities must continue to return
`mode=integration_disabled`, with financial routes unavailable.
