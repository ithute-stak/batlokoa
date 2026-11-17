# Phase 60 — Batlokoa employee assisted client registration preflight

Inspected LoanHub's current source at `apps/backend/routers/company_clients.py`,
`apps/backend/database/schemas/company_clients.py`, and
`apps/backend/services/company_client_service.py` on 2026-11-17.

## Actual LoanHub API
`POST /api/v1/company-clients` accepts
`AssistedCompanyClientCreate` and requires a verified lending staff role,
company and branch. Core fields include personal details, birth date,
national ID or passport, phone, employment status, optional debt and bank
information and explicit sharing/credit-check consent. New borrower creation
may require a temporary password.

## Important risk discovered
LoanHub's existing `create_assisted_company_client` service matches an
existing global person by national ID. If birth date and surname match,
it can reuse a borrower and **modify shared borrower employment, banking and
external debt data** before creating the company-client link. That is too
high risk to activate automatically while historical national-ID collisions
and legacy loan integrity are under review.

## Implemented
- Server-side validated `ClientRegistrationDraft` and
  `prepare_client_registration`.
- Active employee, company/branch and lending-role checks from Phase 54.
- Input constraints for identity references, required fields, age/date,
  salary numeric validity and consent booleans.
- An explicit `RegistrationPreflight` that **always returns can_submit=false**
  and requires manual or separately reviewed identity matching.
- Synthetic tests for unauthorized branch access, borrower impersonation,
  invalid identity/income and non-activation.
- No write endpoint, no saved personal data, no production registration.

## Next
Build a trusted duplicate/legacy identity review API in LoanHub, with explicit
side-effect-free preview and reviewed conflict handling. Then create an
idempotent staff registration workflow, checked against existing borrower,
client-account and legacy records, with audit trails and no global borrower
profile overwrites. Only after staging certification should an authorized
Batlokoa employee submit registrations.

Loan applications, loan offers, payments and disbursements remain disabled.
