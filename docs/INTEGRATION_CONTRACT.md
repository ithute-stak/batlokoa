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

## Phase 5: protected customer loan route (opt-in test boundary)

The `GET /api/v1/me/loans` endpoint now has an authenticated implementation in `backend/app/customer_loans_api.py`. **The default deployment configuration remains HTTP 503** and the current Flutter app remains demo-only.

A trusted server bootstrap must explicitly inject a `ReadRouteConfig` into `app.state.loan_read_config` with an approved HTTPS issuer, Batlokoa-specific audience, trusted RS256 verification key and `LoanReadService`. The service must use a protected customer directory and a LoanHub **borrower-scoped** token broker. There is **no** environment variable that switches this on, no runtime wiring to the real provider, no hardcoded credentials and no direct client-supplied tenant/customer ID.

When a properly configured test bootstrap is injected, the gateway validates a bearer access token before invoking the server-side tenant mapping and read-only LoanHub adapter. Missing/invalid tokens return 401, unauthorized tenant mappings return 403 and upstream unavailability returns 503. A successful response returns only validated loan summaries with `Cache-Control: no-store`. It does **not** display demo loan balances as live values.

**Do not install the test configuration on a public deployment.** Before production access, confirm a reliable OIDC key-discovery/rotation process, real borrower account linking, secure token exchange or consented borrower sessions, server-held session cookie and CSRF controls, replay prevention, audit logging, threat modelling and the exact LoanHub staging access permissions. A token for a LoanHub staff or administrator must never be used for customer loan retrieval.

IthutePay and all finance mutations remain disabled independently.

## Phase 7: two-party verified LoanHub borrower linking (contract only)

Inspected LoanHub's existing `apps/backend/routers/ithute_auth.py`: its `POST /api/v1/auth/ithute/link` requires an authenticated **local LoanHub user session** and a separately validated central !thute Auth token, checks that no different LoanHub user already owns that central subject, and records account-link audit evidence. LoanHub also exposes `GET /api/v1/borrowers/me` under a borrower-role session. These facts are useful for a future Batlokoa customer onboarding flow, but neither endpoint by itself proves Batlokoa tenant membership.

The Batlokoa `backend/app/account_linking.py` module now describes an internal **two-proof account-linking transaction**:

1. Start with a centrally signed subject already validated by the Batlokoa gateway (the module does not accept raw user-supplied JWT claims).
2. Require an independently authenticated LoanHub `BORROWER` account proof for the **same central subject**. Verify the actual LoanHub user-to-borrower profile binding server-side; never infer it from a phone, email, ID number or user-entered UUID.
3. Require explicit recent customer consent referencing the exact borrower and Batlokoa tenant.
4. Recheck active Batlokoa tenant membership using an independent server-side verifier.
5. Persist a mapping with transactional unique constraints for both the central subject and the `(tenant_id, borrower_id)` pair, and reject proof replay and ambiguous relinking.
6. Retain immutable consent evidence and auditable link/revoke records in the eventual production store; require fresh dual proof for any relink.

Unit tests exercise valid matching proofs, cross-tenant denial, role mismatch, subject mismatch, expired evidence, consent mismatch, duplicate links and replay.

**Default behaviour remains disabled:** No customer-linked account table, no production persistence, no trusted LoanHub proof broker, no actual OIDC login flow, no public linking route, and no live customer loan retrieval are installed by this phase. `DisabledLinkStore` rejects every link request. All financial endpoints retain their existing fail-closed posture and IthutePay remains disabled.

### Remaining production prerequisites

- Verify the central Auth application registration, OIDC keys, issuer/audience and secure product session handling.
- Create a production PostgreSQL mapping table with the required unique indexes, audit metadata, consent records and proof-replay constraints, plus integration tests against the real database.
- Implement a reliable server-side LoanHub borrower-role proof against actual linked account state and server-authoritative company membership.
- Ensure token/session issuance does not reuse admin/staff credentials as a customer borrower session.
- Review account recovery, unlinking, revocation, stale/locked accounts, simultaneous linking and support escalation.
- Keep all Batlokoa UI branding sourced from official company logo and verified brand colours rather than temporary placeholders.

## Phase 8: persistent PostgreSQL borrower mapping and revocation

Files: `backend/migrations/001_customer_account_links.sql`, `backend/app/link_store.py`, and `backend/tests/test_link_store_postgres.py`.

The new **opt-in** async PostgreSQL store implements both the `AtomicLinkStore` and `CustomerDirectory` contracts with two tables:

- `customer_account_links`: immutable mapping from approved central issuer+subject to one LoanHub borrower and tenant; globally unique issuer/subject, tenant/borrower, one-time proof digest and consent-reference digest. Revoked entries are **retained** to prevent silent reassignment.
- `customer_account_link_events`: separate append-only link/revoke audit records, written in the same database transaction as the corresponding mapping change. Do not grant runtime DELETE/UPDATE on audit events.

Only SHA-256 proof and consent reference digests are stored, not raw central access tokens, passwords, National IDs or original evidence strings. Operational consent documents and proof records must be maintained by a separately approved evidence service with appropriate access and retention controls; a digest alone does not constitute a complete compliance record.

### Safe operation

1. Apply the SQL migration through a separately privileged migration job; application startup does **not** create or modify tables.
2. Supply a dedicated least-privileged PostgreSQL connection pool via trusted server bootstrap. There is **no** database connection in the public app by default and no environment flag to bypass authentication.
3. Attach the store to `AccountLinkService` only after verified borrower-role proof, genuine customer consent and independent Batlokoa tenant membership validation are available.
4. A verified user's own revocation can be performed through the internal `revoke_self` method. No public revocation endpoint is exposed. Revocation removes the mapping from active lookup immediately, but the uniqueness reservation stays in place.
5. To support future recovery/relink, introduce a separately reviewed dual-authorisation procedure and append-only audit process. Do not delete old mappings or permit silent reassignment.
6. Use database privileges, encrypted backups, secret management, audit monitoring and migration rollback plans in production.

The GitHub Actions workflow runs separate **real PostgreSQL tests** (temporary isolated schemas) for unique keys, concurrent linking, audit transaction rollback, linked lookup, revocation and replay rejection. Existing gateway and Flutter checks continue independently.

**Remaining blockers:** real identity/session token broker, signed borrower proof, tenant verifier, compliance evidence storage, production database migration, and staging acceptance tests. `GET /api/v1/me/loans` remains disabled, and IthutePay still cannot move money.

## Phase 9: central !thute Auth verification and opaque BFF sessions

Verified against the current LoanHub source `apps/backend/services/ithute_auth_service.py`: central access tokens use a trusted JWKS key selector, RS256 signatures, exact issuer/audience, a UUID `sub` (person) and UUID `sid` (central session), and `token_use=access` with `iat`, `nbf`, and `exp` claims. The reference issuer is `https://auth.ithute.co.ls`; Batlokoa's separate audience must be registered and verified before live use. LoanHub's audience (`loanhub`) is **not** accepted for Batlokoa.

`backend/app/auth_verification.py` implements a strict verification component with an injected, trusted signing-key source and positive/negative tests against test-generated RSA keys. Live JWKS discovery, HTTPS allowlisting, bounded refresh/caching and key rollover need an independently reviewed configuration before deployment.

`backend/migrations/002_customer_sessions.sql` and `backend/app/sessions.py` add an **internal**, separately provisioned PostgreSQL-backed session lifecycle. After independently verified central authentication and an active linked customer mapping, it may issue an opaque random session handle with at most a 15-minute lifetime bounded by the central token's expiration. Raw session handles and CSRF tokens are never persisted; only hashes are stored. Session lookup rejects expiration and account revocation. The database stores permanent central `sid` revocation tombstones, and serializes session issuance against central revocation using transactional advisory locks. Internal revoke helpers support logout and central-session invalidation.

Tests use a disposable PostgreSQL instance to verify issuance, separate CSRF proof for state-changing calls, invalid or absent mapping, expiry, logout, unlinking, and central session revocation. A cookie-header helper documents `Secure; HttpOnly; SameSite=Strict` with the `__Host-` prefix.

**No login flow is enabled.** These components are not registered with FastAPI or Flutter. The production route `GET /api/v1/me/loans` remains default-disabled; session issuance must never implicitly establish a LoanHub borrower credential. No real central signing keys, customer identities, or OAuth tokens are committed.

### Remaining controls before production

1. Register Batlokoa as a distinct client with !thute Auth, verify signed OIDC configuration and approved redirect URIs, and use Authorization Code + PKCE with server-mediated HttpOnly sessions. Validate OIDC state/nonce, code exchange, refresh/re-authentication, and token lifetimes.
2. Provision and harden the central JWKS source, maintain an issuer allowlist, key rotation, outage handling, and audit metrics. Never use unverified key URLs from the access token.
3. Apply migrations through a privileged job to a dedicated database; bootstrap a least-privilege, secret-managed pool. The app does not create tables at startup.
4. Integrate and authenticate central session revocation events (and invalidate sessions when central logout/revocation occurs). Never trust a client-originated revocation `sid`.
5. Implement a CSRF-checked authenticated session middleware; control trusted host, proxy origin, SameSite constraints, strict CORS, cache headers and anti-replay. No cross-origin cookie access.
6. Verify independent LoanHub borrower-role proof and tenant membership before mapping or displaying actual loans. No admin session may be reused as a borrower credential.
7. Preserve the official Batlokoa Financial Services logo and verified brand palette throughout the mobile/web application; the backend session changes do not modify visual branding.

IthutePay remains disconnected and all write actions remain disabled.
