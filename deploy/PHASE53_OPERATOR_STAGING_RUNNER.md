# Phase 53 — Operator-controlled staging probe execution

`backend/app/staging_probe_runner.py` connects Phase 49's credential mount
metadata preflight to Phase 52's read-only LoanHub probe. The operator must
supply an independently approved exact staging origin, a **different**
production origin, an approved non-customer staging borrower and a valid
approval window. The runner refuses insecure, missing and symlinked files;
re-checks descriptor metadata and reads credentials only after preflight.
The token is read in process and never included in the returned result.

## Operating requirements

- Use an isolated, operator-managed staging runtime, **not** the public demo
  process. Provision token and trusted verification public key separately as
  private, read-only mounts; do not store them in images, Git or CI.
- Keep the approved staging origin in deployment configuration protected from
  public modification. The `operator_approved` input is only a safety gate,
  **not** proof of approval or environmental isolation.
- Invoke `run_approved_staging_probe` from a privileged operator harness
  passing a `StagingCredentialManifest`, both independently configured
  origins and explicit authorization. No public HTTP endpoint or automatic
  launch is provided in this phase.
- A `verified_read_only` outcome means one protected read path worked at
  invocation time. Record only outcome, timestamp and a redacted evidence
  reference. Do not log token, UUID, loan amount or response body.
- Revocation tests still require a LoanHub administrator to revoke the test
  session and rerun the verification with that **same** credential.
  Session-version reset, wrong borrower, other company, outage, payment
  disabled and public demo status must be separately verified.
- The Phase 50/51 acceptance gates do not establish evidence authenticity or
  production release approval. Independent reviewer sign-off is mandatory.

Nothing in Phase 53 deploys code, creates credentials, authorizes payments,
modifies an existing borrower or enables financial functionality.
