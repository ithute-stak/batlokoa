# Phase 59 — Batlokoa staff client directory (read-only)

Verified against LoanHub's current `apps/backend/routers/company_clients.py`
and `database/schemas/company_clients.py` on 2026-11-17.

The staff-specific endpoint is `GET /api/v1/company-clients`. LoanHub
already enforces active company membership, lending role, and branch scope
through `get_tenant_context`, `require_tenant_roles` and its client query.
The response contains sensitive fields; Batlokoa must expose only the minimum
required to render an authorized client list.

## Implemented

`backend/app/loanhub_staff_clients.py` implements an internal **read-only**
LoanHub adapter requiring a verified Batlokoa staff identity and backend-held
LoanHub staff access token. Requests include the server-derived
`X-Company-ID` and `X-Active-Role`, and a verified branch filter for a
branch-scoped employee. Never accept these values from the Flutter request.
Management roles can have verified company-wide scope. The adapter verifies
every returned client's company and, for branch-constrained staff, branch.
It rejects cross-tenant responses, duplicate client accounts and unexpected
shapes, and returns only account UUID, reference, display name, branch, status
and company UUID. No national ID, balances, bank account or loan history are
returned to Flutter by this adapter.

Network-free tests simulate success, wrong company/branch, invalid records,
duplicate IDs and upstream denial.

## What remains disabled

No public Batlokoa client endpoint or Flutter client list is registered yet.
The default Batlokoa staff session remains a staging-only, in-memory adapter.
This phase does not enable client creation, financial writes, applications or
offers. Real LoanHub staging and end-to-end integration require reviewed
operator configuration and security acceptance.

## Upcoming workflow

- Add an opt-in authenticated BFF route that obtains the server-managed staff
  session, re-verifies it against LoanHub and passes only an approved token and
  company/branch to the directory adapter. Require HTTPS, session expiry,
  auditing and rate limits.
- Display client names and reference numbers rather than internal IDs.
- Confirm branch name mapping using LoanHub's real branch endpoints.
- Add a separate safeguarded client creation adapter using
  `POST /api/v1/company-clients` and its
  `AssistedCompanyClientCreate` contract, after duplication/legacy ID checks.
- Implement staff loan applications with LoanHub's existing
  `POST /api/v1/company-clients/{account_id}/internal-loan-requests`
  after verifying the exact service schema and approvals.

LoanHub is still the authoritative system for lending decisions and audit.
