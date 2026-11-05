# Phase 50 — Controlled staging acceptance evidence

This change provides an **offline evidence completeness checker**, not a live
acceptance runner. Synthetic CI inputs demonstrate validator behavior only.
They must never be copied into a production acceptance certificate.

## Required real staging observations

An authorized operator must perform all of the following with a designated
non-customer test borrower and the approved LoanHub deployment:

- Approved borrower login; same-company read-only loan result
- Cross-company and wrong-borrower refusal before any loan lookup
- Logout and revoked-session-JTI refusal
- Session-version change refusal after password/session reset
- Expired token refusal and upstream outage fail-closed behavior
- Separate public-demo financial route 503 and payment-disable assertions

Obtain an independent security reviewer and durable redacted evidence references,
record the observation timestamps, and do not put identifiers for actual
customers, access tokens, passwords, or loan balances in GitHub.

The checker in `backend/app/staging_acceptance_evidence.py` flags incomplete,
duplicate, stale, failed or unreviewed observations. It does not authenticate
an operator, check the authenticity of evidence references or call LoanHub.
The acceptance decision has no production activation capability and always
sets `production_activation_authorized=False`.

## Next operational gate

Only an approved staging deployer with explicit change approval should mount
the Phase 49 secrets and carry out the real acceptance sequence. Confirm LoanHub
session revocation against the running API, not merely synthetic tests. A
separate security signoff is required before any customer-data activation.
IthutePay remains independently disabled pending merchant, settlement, and
reconciliation approval.
