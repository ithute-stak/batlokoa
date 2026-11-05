# Phase 52 — Read-only LoanHub staging probe

The module `backend/app/staging_loanhub_probe.py` implements an
**explicitly invoked** in-process probe. It is **not** attached to the public
Batlokoa gateway and has no CLI, credential loader, or deployment hook.

The caller must provide a pinned, approved HTTPS LoanHub staging origin,
a designated test company's UUID and test borrower's UUID, a trusted
LoanHub RS256 public verification key and a short-lived borrower token.
The boolean `approved_staging` is only a local guard: an operator must
independently verify environmental isolation and actual written approval.
The probe does not establish that the target is truly staging.

With approved inputs, it verifies signature/expiry, LoanHub `/auth/me`,
and LoanHub's company/borrower-context endpoint. It then attempts the
already-existing guarded, tenant-scoped read-only loans adapter. Returned
diagnostics contain neither credentials nor loan balances or identifiers.

A successfully returned `verified_read_only` result is **one observation**
and not a staging acceptance certificate. To certify revocation, an
authorized LoanHub operator must actually revoke the approved staging
session and rerun the probe to establish denial. Wrong-company and
wrong-borrower test cases, expired credentials, outage behavior and all
Phase 50 observations must be independently recorded and reviewed.

Do not use actual customer credentials or a production origin. Do not
commit credential material or attach raw HTTP logs to issues. Do not enable
customer-facing Batlokoa routes or IthutePay based on this probe.
