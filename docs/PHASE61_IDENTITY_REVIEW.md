# Phase 61 — LoanHub read-only identity and legacy screening

Verified source: LoanHub `GET /api/v1/company-clients/existing-loan-check`
requires an authorized lending staff session and returns company-specific
existing loan exposure, borrower and client-link flags and count of matching
legacy capture records.

The new `LoanHubIdentityReview.review` is a backend-only adapter. It uses
the verified staff role and company and validates a permitted branch before
calling LoanHub with the staff credential. It returns only a minimal status,
borrower/client-link flags and legacy count. It does not expose the searched
national ID or any loan, bank, salary or balance data.

**No result permits automatic registration.** Even a clear national-ID lookup
cannot rule out historical identity corruption, duplicate records elsewhere,
or a race with another registration. Phase 60's preflight remains
`can_submit=false`. The LoanHub assisted-create flow can modify an existing
global borrower's employment, debt or bank profile. Before enabling a write,
implement a reviewed LoanHub atomic identity reservation, conflict workflow,
idempotency and audit checks.

No route is publicly exposed; no real customer or loan records are modified.
Network-free regression tests cover clean and legacy matches, malformed
responses, wrong employee branch and upstream access denial.
