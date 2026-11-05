# Phase 49 — isolated staging borrower-token vault

A limited `EphemeralBorrowerTokenVault` is provided for a **single-process
synthetic or explicitly authorized test-account staging environment only**.
It is never mounted into the public gateway and cannot enable customer loan
reads or payments by itself.

The vault requires a pre-provisioned Fernet encryption key, encrypts tokens
in memory, limits entries to 256, limits retention to five minutes, restricts
each record to an exact canonical LoanHub tenant/borrower pair, and calls an
independently configured trusted LoanHub verifier before accepting a token.
A separate broker must **reverify LoanHub on each read** so a newly revoked
LoanHub session cannot continue using an old grant. It supports staging
central-SID revocation and per-borrower revocation.

**Never use this volatile vault for multiworker or real customer production.**
It lacks durable encrypted storage, key rotation, transactional
cross-instance revoke, audit durability, recovery and an approved credential
provisioning flow. Identity and SID binding still depend on the caller having
completed approved OIDC session verification. The staging vault must not be
populated with browser-provided LoanHub credentials or privileged admin tokens.

Before live customer-data activation, replace this with an independently
reviewed persistent token vault using a protected encryption key, purpose-bound
token exchange, a central-user-to-LoanHub-borrower ownership proof, durable
revocation, short lifetimes, retention policy and audit logging. Verify an
approved test borrower against the *live* LoanHub auth endpoint and real
tenant relationship. Access to live customer data requires explicit legal,
security and business approval. IthutePay payments remain separately disabled.

Tests are in `backend/tests/test_phase49_ephemeral_borrower_vault.py`.
No app startup imports or deploy configuration activate the vault.
