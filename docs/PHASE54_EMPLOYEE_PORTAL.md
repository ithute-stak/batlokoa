# Phase 54 — Multi-branch employee portal authorization foundation

## Business requirement
Every authorized Batlokoa Financial Services employee, regardless of branch,
should use the Batlokoa web/mobile app to operate the **existing LoanHub**
workflow: locate and register clients, capture and submit applications, and
prepare loan offers. Each employee gets an individually authenticated session.
LoanHub remains the source of truth for client records, loan decisions, staff
membership, branch assignment, and audit history.

## Verified LoanHub contracts (reviewed 2026-11-17)
- `apps/backend/core/access_control.py`: `get_tenant_context`,
  `require_tenant_roles`, `assert_branch_scope`, `LENDING_ROLES`.
- `apps/backend/routers/company_clients.py`: tenant-scoped company-client
  listing and POST registration, with lending role and branch enforcement.
- `apps/backend/routers/loan_offers.py`: loan-offer creation, amendment and
  withdrawal with lending roles and branch scope.
- `apps/backend/routers/loan_request.py`: borrower-oriented loan request
  lifecycle; **do not assume staff may impersonate a borrower**.
- `apps/backend/routers/borrower_registration.py`: public borrower
  registration is **not** a substitute for verified staff client creation.

Routes, payload schemas, auth mechanism and approval chain must be rechecked
against the exact deployed LoanHub revision before an adapter can be enabled.

## Implemented in this PR
- Pure `VerifiedStaffIdentity` authorization boundary and narrow permissions
  for client reads/registration, application draft and offer preparation.
- Fail-closed checks for active session, verified company, LoanHub lending role,
  authorized branch, and explicit company-wide management scope.
- Negative tests for borrower/cashier impersonation, inactive staff, wrong
  company, wrong branch and forged company-wide scope.

**Not implemented:** actual staff login, verified identity-to-LoanHub mapping,
client creation, financial writes, loan issuance, Flutter staff screens or
production deployment. No new network-enabled route is registered.

## Required implementation sequence
1. Verify LoanHub's current staff sign-in mechanism and effective membership,
   branch and role resolution. Bind a Batlokoa staff session to an independently
   verified LoanHub user identity; never reuse borrower-role credentials or
   expose LoanHub admin tokens to Flutter.
2. Add read-only `/api/v1/staff/me` and branch capability endpoints on an
   opt-in staging configuration, using short-lived session cookies, CSRF
   protection, audit logs and negative tenant/branch tests.
3. Implement server-side client list/search and client registration adapters.
   Use the verified LoanHub company-client schema; handle duplicate national
   IDs safely and never merge legacy records based on national ID alone.
4. Introduce staff application drafts and submission using the actual
   LoanHub lending workflow, after verifying whether employee-originated
   applications are supported or require a dedicated LoanHub API.
5. Introduce staff offer preparation without bypassing approvals or borrower
   acceptance. Add idempotency keys, duplicate-submit protection and
   explicit branch audit metadata.
6. Add responsive employee login, branch selection, client registry,
   application and offer screens to Flutter. Only display server-authorized
   branches and capabilities.
7. Obtain separate staging acceptance for every real read/write. Keep
   customer demo state isolated; leave IthutePay, disbursement and public
   financial writes disabled until separately certified.

## Critical security rules
- Never trust role, user, tenant or branch identity from browser parameters.
- Never grant blanket admin access to employees.
- Never let a staff session call customer-only borrower endpoints as a borrower.
- Never allow local `staff_authorization.py` to override LoanHub's own rules.
- Approval, offer acceptance, disbursement and financial posting require
  separate authorization and are outside Phase 54.
- Every real write requires a trusted server-side audit trail.
