# Batlokoa ↔ LoanHub / IthutePay integration boundary (Phase 1)

**Status: scaffold only. No financial provider is connected.** This gateway is not a production API and must not be exposed to customers. Its financial routes deliberately return HTTP 503 `INTEGRATION_DISABLED` and never simulate approved applications, balances or transactions.

## Responsibilities

- **Batlokoa Flutter UI**: customer experience only; never embed LoanHub tenant admin tokens, payment provider secrets, merchant shortcodes or payment signing keys.
- **Batlokoa integration gateway**: planned customer session verification, Batlokoa tenant-to-customer mapping, input validation, request idempotency, audit metadata, and gateway policy.
- **LoanHub**: only authoritative loan accounts, offer terms, repayment allocation and outstanding balances.
- **IthutePay**: only payment intents, provider confirmations, settlement/reconciliation and payment receipt states.

## Proposed internal API (not connected)

| Route | Purpose | Current behaviour |
|---|---|---|
| GET /healthz | Process liveness only | HTTP 200 |
| GET /api/v1/capabilities | Explicit disabled features | HTTP 200, all false |
| GET /api/v1/me/loans | Authenticated customer loans | HTTP 503 |
| POST /api/v1/loans/applications | Submit loan request | HTTP 503 |
| POST /api/v1/payments/intents | Request authorized payment | HTTP 503 |
| GET /api/v1/me/wallet | Authorized ledger-backed wallet view | HTTP 503 |

Do not assume these routes match existing LoanHub or IthutePay endpoints; adapters will be implemented only after their real schemas, authentication mechanisms, versions, tenant isolation, and payment statuses are verified. `backend/app/contracts.py` defines the preliminary internal schema.

## Mandatory security gate before enabling any route

1. Verify server-side customer identity through a real authentication provider and short-lived authenticated sessions. The Flutter browser must not provide an authoritative `tenant_id` or `customer_id`; derive both from verified claims and a server-side mapping.
2. Check the customer belongs to the Batlokoa tenant before every read, write, loan lookup and payment.
3. Configure separate backend-only LoanHub and IthutePay credentials and least-privilege service identities.
4. Use integer minor units for money and authoritative backend loan offers. Never calculate a final financial balance from demo UI values.
5. Require idempotency, payment-intent state machine, signed webhook verification, deduplication, transactional outbox and reconciliation before recording repayments.
6. Confirm licensing, customer consent, data protection, audited access logs, rate limits, and operational alerting.
7. Switch off demo login and hardcoded balances whenever real customer data is displayed. Staging must not mix fictional and real balances.
8. Publish behind TLS with restricted access and a separate environment configuration. Do not serve this API as a public finance service until it passes end-to-end security review.

## Running the scaffold locally

From the repository root:

```bash
python -m pip install -r backend/requirements-dev.txt
python -m pytest -q backend/tests
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8090
```

Only process liveness and a non-sensitive, disabled-capability report can return success. The current scaffold has no credentials, no stored customer data, no database and no provider traffic.

## Phase 2: cryptographically validated identity and tenant guard (foundation)

The `backend/app/identity.py` module now supplies independently testable primitives for:

- Verifying **RS256-signed** JWTs against a **trusted public key** with a pinned HTTPS issuer, audience, expiration, issuance time and immutable subject.
- Resolving the immutable subject to a customer using a **server-owned mapping directory**, never email, phone or client-supplied tenant fields.
- Rejecting absent mappings, cross-tenant associations and subject mismatches. The default directory contains **zero** customers.

The repository does not yet contain a trusted key-discovery lifecycle, real persistent customer directory, login/session flow, or verified LoanHub-specific read endpoint. Therefore **none of these primitives is wired into a real financial route**, and the existing 503 guard remains unchanged. This is intentional: passing JWT unit tests does not prove production authentication.

### Requirements before activating authenticated reads

1. Confirm Ithute Auth OIDC discovery URL, signing key rotation, token issuer and the **Batlokoa-specific audience**. Do not accept a token minted for IthutePay or LoanHub if it does not target Batlokoa.
2. Store the approved Batlokoa tenant ID and subject-to-customer mapping in a protected backend data store. Verify mapping against the actual LoanHub tenant and customer model.
3. Determine whether the frontend uses a backend-for-frontend session with HttpOnly Secure SameSite cookies rather than browser-held API tokens. Add CSRF protection for state-changing actions.
4. Verify LoanHub endpoint paths, scopes, service credentials, rate limits and status semantics against the actual repository, then implement a strictly read-only adapter with mockable contract tests.
5. Never put authentication keys or per-tenant upstream credentials in the Flutter bundle. Payments remain entirely disabled until the separate payment review and reconciliation phase.

### Test scope

`backend/tests/test_identity.py` tests valid signed JWTs, wrong issuer and audience, invalid or expired claims, wrong signing keys, unsigned tokens, absent customer mappings and cross-tenant isolation. These are local unit tests using test-generated RSA keys, not successful live SSO or LoanHub connectivity.

## Phase 3: tenant-scoped read-only LoanHub service (contract-testing stage)

`backend/app/loan_reads.py` now supplies an internal **read-only orchestration service**. It accepts claims only after they have been verified by the earlier cryptographic JWT validator, derives the customer from the protected server mapping, requires a configured Batlokoa tenant, and passes only that mapped tenant/customer identity to a LoanHub adapter.

The service rejects unauthorized or cross-tenant mappings before making any upstream request. Upstream responses must match the strict LSL `LoanSummary` shape; negative balances, invalid currencies, duplicate loan identifiers, non-list results and excessive record counts are rejected rather than shown as authoritative data. Empty loan lists are valid and do not become fabricated demo balances.

**Not yet live:** The real LoanHub endpoint, response schema, authorization scopes and customer model are not verified. The repository's current `GET /api/v1/me/loans` continues returning HTTP 503. No signed JWT or test stub can bypass that HTTP route. Tests use an in-memory read-only adapter only.

### Required next implementation

Verify LoanHub's actual route path, schema, tenancy checks and service identity, then add an HTTP adapter that translates its real response into `LoanSummary` and call this service only through an authenticated, configured, authorization-gated endpoint. Add provider contract tests, audit logging and strict timeouts. Actual customer data must never be mixed with the Flutter sample dashboard.

## Phase 4: verified LoanHub v2 borrower loan-list adapter

Inspected actual LoanHub repository `ithute-stak/LoanHub` on November 3, 2026:

- `apps/backend/main.py` includes the API router under `/api/v1`.
- `apps/backend/routers/loans.py` declares `GET /loans/`. The `BORROWER` role is restricted at the query to `current_user.borrower_profile.id`. Company staff and superadmin roles have different access and must **not** be used as customer tokens.
- `apps/backend/database/schemas/loan.py` defines `LoanRead` with UUID `id`, `company_id`, `borrower_id`, `status` and decimal `balance`.

`backend/app/loanhub_adapter.py` implements a read-only HTTPS adapter for this **verified endpoint**. It requires a backend-provisioned LoanHub **borrower-scoped token** for the mapped borrower, never an admin token, and compares every returned `company_id` and `borrower_id` to the server mapping. It validates decimal LSL amounts without floating-point rounding; rejects malformed, duplicated and cross-tenant results; enforces a response size and bounded request timeout; and does not follow redirects.

**Not wired into the public Batlokoa API.** The crucial missing capability is a trusted way to obtain and validate a real LoanHub borrower-role session for an authenticated Batlokoa customer, including the subject/borrower link and tenant mapping. The consumer `GET /api/v1/me/loans` route therefore **continues to return 503**. The adapter does not ship with any secrets. It does not use the `X-Company-ID` staff selector or send any tenant header as authority.

Production data validation remains required: prove that the borrower token maps to the precise LoanHub borrower, confirm the expected company UUID and list shape against a restricted staging instance, handle datasets larger than 99 results with a safe paginated design, and introduce auditability, availability monitoring and customer-consent controls. Do not expose the demo app as a banking service.

### Brand system requirement

All new Batlokoa customer screens must inherit the company's approved colour values and official logo from verified brand assets. The payment and loan services do not dictate Batlokoa's frontend appearance. Do not select approximate brand HEX values until the official logo or brand guide has been inspected.
