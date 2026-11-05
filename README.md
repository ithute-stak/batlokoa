# Batlokoa Finance

Mobile-first, responsive Flutter customer application for **Batlokoa Financial Services**.

- Intended domain: **https://batlokoa.co.ls** (DNS/hosting not configured by this repository)
- Android / iOS / responsive web
- UI-first scaffold with **demonstration data only**, not a financial backend
- Future integrations: LoanHub for loans, IthutePay for payments/wallet rails and Ithute Auth for identity

## Run

```bash
flutter create . --platforms=android,ios,web
flutter pub get
flutter run -d chrome
```

`flutter create .` fills in the standard Flutter platform runners for this repository. No secrets are required for the UI demo.

## Screens

Welcome/onboarding, sign-in/sign-up, dashboard, loans, loan application wizard, loan details, wallet, money actions, bills, payment confirmation, activity, notifications, support, profile and security/settings.

## Security and integration status

All balances, transactions and loan decisions are **sample data**. Payment and application buttons display demo confirmations and never move real money or submit credit applications. Do not ship as a financial service before integrating licensed partners and production controls, including KYC, consent, secure session storage, transaction authorization, server-side verification, reconciliation, audit trails and accessibility tests.

## Responsive layout

Narrow screens use a bottom navigation bar; wider screens use a navigation rail and constrained content. Content adapts from one to multiple columns.

## Brand

The UI uses a provisional deep-teal and mint visual identity until official Batlokoa artwork is supplied.

## Next UI iteration

The additional customer-preview flows are implemented in `lib/customer_flows.dart`:

- Three-step identity-verification preview with acknowledgement checkbox
- Notifications page with unread filter
- Security and communication preferences preview
- Help centre with FAQs and a local-only support form

These flows are reachable from **Profile**. They do not capture real IDs, change credentials, or send requests. Real provider and identity integration remains a separate task.

### Responsive validation

The test suite now exercises 320, 375, 430, 768, 1024 and 1440 logical-pixel viewports, in addition to core screen-navigation checks. GitHub Actions is configured to run analyzer, tests and web build. Passing status must be confirmed in the Actions tab.

### Web deployment

For a test web build:

```bash
flutter pub get
flutter test
flutter build web --release
```

Upload the contents of `build/web` to a TLS-enabled static host serving `batlokoa.co.ls`, with history fallback to `index.html` for client-side routes. Configure DNS, TLS certificates, security headers, release caching and an explicit environment-specific API endpoint before live release. Merely declaring the domain here does not register or configure it.

## UI iteration: transaction review and stronger loan forms

- Added `lib/payment_review.dart` as a separate transaction-review route.
- Wallet money actions and bill-payment forms now pass entered amounts/references to a review screen before a **demo-only** confirmation.
- The customer can return to the form using `Edit details`.
- Loan application step 2 rejects empty income sources and nonpositive income; its review step shows what the customer entered.
- Added `test/payment_review_test.dart` for review and customer-navigation coverage.
- **No money or credit request is submitted**. This is not a wallet ledger, licensed payment service or production KYC flow.

### Before production

Confirm `flutter analyze`, `flutter test` and `flutter build web --release` pass on GitHub Actions. These commands have **not been run successfully by the authoring assistant** in this iteration. Validate at narrow viewports and with text scaling, keyboard navigation and screen readers. Then add backend state, authorization, error handling, service fees, beneficiary verification and compliance requirements.

## Phase 6: Customer-loan Flutter presentation boundary

- `lib/customer_loan_data.dart` defines validated, read-only Batlokoa gateway loan summaries denominated in LSL minor units.
- `lib/customer_loans_screen.dart` provides dedicated loading, empty, error/retry, and verified loan-list states. No fabricated monetary values are displayed when the repository is disabled or unavailable.
- The main **My loans** screen offers a **View verified loans** entry point and explicitly labels existing loan figures as **demo only**.
- The default `DisabledCustomerLoanRepository` intentionally fails closed. No browser API token, LoanHub administrative credential, real account, payment rail, or production authentication flow is added.
- Future production repository wiring must use an approved same-origin authenticated session to Batlokoa's gateway. Do not set API authorization by injecting tenant/customer IDs from the Flutter UI.
- Loan details and repayments remain demonstration-only; real instalment terms require separately verified LoanHub detail contracts, and IthutePay remains disabled.
- Official Batlokoa Financial Services logo, artwork and colour values must be applied only using verified company assets. Current code still contains provisional colours; this phase does not claim a completed official brand rollout.

## Staging OIDC assembly

The staging auth assembly composes approved OIDC client metadata, the pinned JWKS provider, PostgreSQL-backed login/session stores and secure token exchange. It does not activate login routes or financial operations. Real provider discovery and Batlokoa registration remain unverified. The normal app stays disabled by default.

## Phase 14: database and signing-key preflight

The new read-only `inspect_staging_schema` checks for all five required PostgreSQL tables and essential uniqueness/foreign-key constraints after a privileged migration. It never applies migrations or enables live endpoints. CI runs this against an isolated disposable PostgreSQL schema, including deliberate missing-constraint scenarios.

`ApprovedJwksSnapshot` accepts only a separately approved static RSA/RS256 public-key set, supports overlapping key IDs during a reviewed rotation, and refuses unknown, duplicated or unsupported signing keys. No real !thute Auth keys are included, fetched or activated. JWKS retrieval policy, staging client registration, revocation notifications, deployment privileges and live borrower authorization still require separate verification. All customer financial endpoints and IthutePay remain disabled.

## Phase 15: localhost-only staging preview and acceptance tests

The repository now contains `Dockerfile.gateway`, `compose.staging.yml` and `scripts/smoke_staging.sh`. The Compose stack packages the existing static Flutter Web preview and a separate **disabled** FastAPI gateway into independent containers, with both exposed only on `127.0.0.1` by default. It provides **no production credentials**, no database provisioning, no authenticated session configuration, no LoanHub connection and no payment capability. It is not a public TLS deployment.

### Reproduce in an isolated development or staging host

Build the Flutter Web artifact using a reviewed Flutter toolchain, then run:

```sh
flutter pub get
flutter build web --release
docker compose -f compose.staging.yml config --quiet
docker compose -f compose.staging.yml up -d --build
bash scripts/smoke_staging.sh
docker compose -f compose.staging.yml down --remove-orphans --volumes
```

The staging smoke script verifies the Flutter site and API health, confirms `/api/v1/capabilities` reports every financial feature disabled, and checks that all sensitive auth, loan, wallet and payment endpoints still return HTTP 503. The same stack test is part of GitHub Actions and fails if anything unexpectedly becomes available.

**Operational limitations:** The gateway preview does not share the Flutter Nginx origin, and the web UI remains demo-only. A public production deployment requires externally managed HTTPS, registered OIDC callback, real provider discovery/JWKS, reviewed database migrations and credentials, end-to-end authenticated browser tests, tenant-link and borrower-role authorization, logging/monitoring and release rollback instructions. Never expose the preview API ports directly to the internet or enable transactions as part of this preview.

## Phase 16: same-origin HTTPS staging and session-status boundary

The opt-in `compose.staging.https.yml` adds an Nginx HTTPS edge on loopback port 18443. It serves Flutter Web from the web container and sends `/api/` to the FastAPI gateway under **the same HTTPS origin**. Neither backend container publishes a host port. The edge requires separately provisioned TLS certificate files: `fullchain.pem` and `privkey.pem`. No certificates, live signing keys, customer details or credentials are committed.

A controlled staging operator can build Flutter assets and start the preview with:

```sh
flutter pub get
flutter build web --release
export BATLOKOA_STAGING_TLS_DIR=/absolute/path/to/approved-staging-certificates
docker compose -f compose.staging.https.yml config --quiet
docker compose -f compose.staging.https.yml up -d --build
docker compose -f compose.staging.https.yml down --remove-orphans --volumes
```

By default only `https://127.0.0.1:18443` is published. A publicly reachable staging domain requires a reviewed front-facing TLS/reverse proxy plan, valid trusted certificate, approved DNS and network/firewall controls; the loopback stack is **not** a public deployment. CI generates a **disposable self-signed certificate only for local acceptance tests** and verifies the same-origin gateway routes remain 503 for login, verified loans, wallet and financial writes. Do not use `curl --insecure` in real customer clients.

Flutter now includes a separate read-only **Secure sign-in status** view and a `GatewaySessionRepository` contract that calls `GET /api/v1/auth/session` only on an operator-provided HTTPS origin, rejects malformed/disabled responses, and never sends bearer credentials or tenant IDs. By default the view uses `DisabledSessionRepository`: it performs no network operation and reports that secure sign-in is not connected. No automatic login, token storage or live loan retrieval was enabled.

Outstanding external prerequisites: verified !thute Auth client registration, provider metadata, trusted HTTPS host/certificate, approved customer-session bootstrap and database configuration, loan-borrower authorization, official Batlokoa Financial Services logo and approved palette. IthutePay remains disabled.

## Phase 18 — six-screen design system and responsive polish

The six existing Flutter screens now use centralized **provisional** theme tokens in `lib/batlokoa_design.dart`, rather than duplicating colour values, field styling and tap-target dimensions. Typography, button minimum heights, card spacing and responsive horizontal page gutters have been standardized. Bill-service cards allow longer captions at increased text scale. The sign-in, Home, Loans, Wallet, Pay bills and Profile paths remain demo-only; no real authentication, account data or payments were activated.

**Branding status:** The teal/mint palette is deliberately marked provisional in the code. Official Batlokoa Financial Services logo files and approved red/blue/grey/white hexadecimal palette still need confirmation before a brand rollout. Do not substitute a generated logo or claim these colours are official. New widget tests verify theme invariants, mobile/desktop navigation and demo disclosures, while existing CI continues to exercise API, PostgreSQL, web and HTTPS staging protections.

## Phase 19 — large-text accessibility and safer input ergonomics

Loan account detail and payment-review label/value rows now adapt to narrow cards or increased text scaling by stacking the text instead of squeezing amounts beside labels. Shared `ActionButton` no longer fixes its height to 50 pixels, allowing labels to wrap at larger accessibility font sizes. Demo sign-in and demo financial forms declare appropriate keyboard Next/Done actions and decimal numeric keyboard hints for amounts.

Widget tests cover doubled text size in account details, enlarged payment summaries, 320px loan navigation and keyboard action configuration. This stage changes presentation only. It does **not** store sensitive login credentials, submit loan applications, retrieve balances or enable payments. The provisional colour palette is still not the verified Batlokoa brand.

## Phase 20 — polished financial preview surfaces

Home and Wallet use the shared `DemoBalanceCard`, prominently displaying `DEMO ACCOUNT` and a disclaimer alongside every fictional LSL balance. The loan summary clarifies that the 38% progress figure is illustrative, while Loan details now display a separate three-instalment `DemoRepaymentPreview` with prominent sample wording. Wallet actions use a responsive two-column/four-column `DemoWalletActions` layout with text-scaling-aware tile height. Profile provides a clearer Account and support section and a visible unverified-account lock icon.

The widgets are purely presentational. Their demo action callbacks continue to navigate to non-transactional preview forms; no real bank balance, LoanHub borrower data, account verification or IthutePay payment was activated. Styling retains explicitly provisional colours until official Batlokoa brand assets are approved. Widget tests ensure all sample amounts are identified as fictional and wallet action buttons retain demo-only navigation.

## Phase 21 — connected demo customer journeys

The **Home → Loans → Loan details → Sample activity → Back to loans** journey now provides clear demo navigation through the existing screens. Home recent-activity rows open the searchable fictional transaction-history view. Home and Pay bills share the same bill-service routing: the Transfers shortcut opens a demo Send money form; More explicitly shows a disabled preview; other services open existing bill payment previews. This corrects the earlier difference between Home and Pay bills shortcuts.

Dedicated Flutter widget tests cover this cross-screen navigation, the return path and both shortcut exceptions. All account balances, loan schedules, transaction histories and payment reviews remain demo-only; nothing is submitted to LoanHub, !thute Auth or IthutePay.

## Phase 22 — retained tab positions and unsent preview forms

The five demo tabs now use `IndexedStack` to keep their widget trees alive while the user switches tabs. This preserves in-session list scroll position without introducing persistent storage or retaining any real customer data.

Demo loan applications, wallet transfers and bill-payment forms use `DemoDraftGuard`: a back gesture or navigation attempt on a changed form asks the user to **Keep editing** or **Discard draft**. Blank forms exit normally, while the confirmation dialog explicitly states that no payment or application has been submitted. Drafts are in-memory only, and returning from a read-only payment review does not clear the form. Flutter tests exercise tab state retention, editing/discarding and normal blank-form navigation at narrow mobile sizes.

**No live loan applications, balances, real authentication or IthutePay payments were enabled.** The current colours remain provisional pending official Batlokoa brand artwork and codes.

## Phase 23 — accessible demo form error recovery

The loan affordability step now shows a persistent, visible inline error summary instead of a temporary snackbar when required demo income details are missing or invalid. The error clears when the user resumes editing, without resetting earlier loan choices. The shared `DemoFormError` component marks the error as a screen-reader live region. Transfer and biller payment previews now validate fields as users interact with them, so an invalid amount can be corrected before reviewing a non-transactional confirmation.

Flutter widget tests cover loan error recovery, payment amount correction and accessibility semantics. This is **frontend-only** preview logic; production financial values, compliance checks and account permissions must still be validated by their authorized services. No real LoanHub loan application, login or IthutePay payment is enabled.


## Phase 34 — inactive customer-loan gateway adapter

`lib/gateway_customer_loan_repository.dart` provides an **explicitly opt-in**, read-only Flutter contract-test adapter for a future Batlokoa HTTPS customer gateway. The adapter is **disabled by default**; the customer-facing `CustomerLoansScreen` still uses `DisabledCustomerLoanRepository` and makes no network requests.

**Important:** `/api/v1/customer/loans` is a **provisional candidate contract**, not a verified production LoanHub endpoint. Do not enable this client against a real service until the Batlokoa gateway route, HTTPS origin, server-owned tenant/customer identity, authenticated session and borrower-level authorisation have all been independently verified. The client cannot confer authorisation.

The adapter makes at most a read-only GET, never attaches a bearer token, tenant or customer ID, refuses redirects, non-JSON/unexpected HTTP responses, oversized data, invalid currencies and malformed or duplicate loan records. An unavailable or non-authorised response never falls back to demo balances. The new `test/phase34_gateway_customer_loan_test.dart` exercises these failure paths entirely with mocked HTTP; it does **not** establish a working LoanHub connection.

Before activation: confirm the actual route and response schema with the LoanHub/Batlokoa backend team; separately test cookie/session handling and same-origin CSRF protections; enforce tenant and borrower permissions on the server; require verified HTTPS; perform staging end-to-end authorization and information-leak tests. Financial writes and IthutePay stay disabled.


## Phase 35 — gateway route reconciliation and authorization gates

The Batlokoa backend currently exposes the **disabled-by-default** customer-loan read route at `GET /api/v1/me/loans` (see `backend/app/customer_loans_api.py`). Phase 35 aligns the opt-in Flutter contract-test adapter with that actual repository route, instead of the non-existent candidate `/api/v1/customer/loans`. This is a repository-level contract reconciliation, **not** validation of a production LoanHub connection.

**Authentication gap:** The existing gateway loan route requires an RS256-verified bearer token and backend-owned tenant/customer lookup. The Flutter contract-test adapter deliberately does not hold bearer credentials. Thus, enabling only its opt-in flag is insufficient: requests will be denied unless a separately approved and tested same-origin customer-session BFF contract is implemented. Do **not** insert service credentials or customer/tenant IDs in Flutter to bypass that gap.

Authorization tests additionally require failure without valid identity, refusal of caller-supplied tenant/borrower hints, cross-tenant and wrong-subject denial before any upstream call, and financial-write endpoints staying disabled. Production activation remains blocked pending real borrower-scoped LoanHub credentials, session gateway design, verified account linking, and security review.


## Phase 36 — opt-in browser-session customer-loan read boundary

The backend now includes a separate `GET /api/v1/me/loans/session` endpoint which is **HTTP 503 by default**. It is deliberately not wired to Flutter and does not activate OIDC or LoanHub.

After a separately reviewed bootstrap explicitly installs `SessionLoanReadConfig`, the endpoint checks same-origin browser fetch metadata, an opaque `__Host-batlokoa_session` cookie, and a server-resolved, non-revoked customer account link. The configured tenant must match that trusted session's tenant; borrower IDs and tenant headers/query parameters never decide access. A read-only LoanHub adapter would then supply data and must use an approved borrower-scoped backend credential, never an administrator token or Flutter token. Invalid records, missing sessions and service failures fail closed, with no demo-balance substitution.

The existing signed-bearer `GET /api/v1/me/loans` path is unchanged. Flutter's Phase 35 adapter is still disabled by default and is **not** yet wired to this new cookie-session route. A future phase must select one approved browser contract, verify actual identity-provider registration and token/session revocation, integrate a real borrower-specific backend credential broker, and perform audited end-to-end tests with separate tenant identities. The same-origin fetch-header policy is intentionally restrictive and requires browser-compatibility checks before any activation. All financial writes and IthutePay remain disabled.


## Phase 37 — central revocation and borrower credential isolation

Every PostgreSQL customer-session resolution now checks the central session-revocation table in addition to session/link revocation and expiry. This is a defense-in-depth check: even if a session row were not marked revoked, a centrally revoked identity-session ID must no longer resolve to a borrower. Tests validate the SQL policy and the lookup behavior.

The existing backend-only LoanHub read adapter now converts credential-broker errors into a generic `LoanHubReadError` and makes no upstream request when the broker fails or reports no borrower credential. Mocked tests verify that credentials are requested separately for the exact tenant/borrower mapping, borrower revocation prevents subsequent reads, and internal broker error strings are not surfaced as user-facing messages. These tests do **not** prove the real credential issuer's scopes or revocation latency; external integration must still validate those properties.

Staging smoke tests now explicitly require `/api/v1/me/loans/session` to stay HTTP 503 in the unconfigured deployment. Production OIDC, borrower-token provisioning, authorization and reconciliation are not activated. Real LoanHub customer data and IthutePay remain disabled.


## Phase 38 — PostgreSQL-backed session-to-loan HTTP integration tests

`backend/tests/test_phase38_session_route_postgres.py` exercises the actual FastAPI session-loan route and actual PostgreSQL `PostgresSessionStore` and `PostgresCustomerLinkStore` in a disposable isolated schema. The suite verifies that the trusted session's linked borrower and tenant are used; HTTP-origin, customer and tenant spoofing fail or cannot alter authorization; individual logout, central revocation records, and account unlinking stop subsequent loan reads; and upstream exceptions never produce fake balances or leak internal errors.

The CI `postgres-link-store` job runs this test file against its ephemeral PostgreSQL 16 service alongside the existing migration and account-link tests. Only a deterministic fake LoanHub adapter is used. Passing does **not** mean production LoanHub credentials, token expiry, external revocation events, IdP login, or actual borrower data are connected. The session loan API remains **disabled by default**, and IthutePay and all financial writes stay disabled.


## Phase 39 — LoanHub borrower credential verification gate (disabled)

A repository inspection of LoanHub's `apps/backend/routers/loans.py`, `core/security.py` and `core/access_control.py` confirms the effective customer-read permission derives from the **authenticated LoanHub user's active database account, effective borrower role, borrower profile and revocation checks**. The API's `GET /api/v1/loans/` filters loan rows by that borrower profile. A bearer JWT's standalone, unverified `role` or `scope` label is **not enough** to prove borrower access.

The new backend-only `GuardedBorrowerTokenSource` contract validates short-lived, per-request broker assertions for exact tenant and borrower IDs, effective borrower role, current account/session validation, expiry, broker-check freshness, and syntactically safe token data. It can be composed with the existing read-only `LoanHubBorrowerReadAdapter` without putting any bearer token in Flutter. Contract tests simulate administrative roles, mismatched borrowers/tenants, expired and revoked grants, broker failures and repeat revocation checks. No real tokens or customer data are used.

**Important production limitation:** a `VerifiedBorrowerGrant` is an assertion supplied by a *trusted server-side broker*, not cryptographic proof by itself. This repository does **not** implement or enable the broker, nor does it validate real LoanHub issuer signatures, local session versions or refresh-token revocation. A production implementation must perform those checks against actual LoanHub authorization and account state, issue borrower-only credentials, honor revocations promptly, and prove no privileged role can be used at the customer endpoint. The new guard is not registered in the running gateway and all loan reads and IthutePay financial operations remain disabled by default.


## Phase 40 — disabled trusted-verifier borrower broker orchestration

`backend/app/loanhub_grant_broker.py` adds `LoanHubBorrowerGrantBroker`, a server-only boundary between a tenant/borrower-scoped token vault, a trusted LoanHub authorization verifier, and the already-present `GuardedBorrowerTokenSource`. It rejects unavailable tokens, mismatched account/tenant/borrower identities, effective non-borrower roles, inactive accounts, revoked sessions, stale verifications, and expired tokens. It does not cache identity assertions; a verifier must recheck LoanHub user and token status on each call. Mocked tests cover allow/deny paths through the read-only LoanHub adapter.

**Not production-connected:** the trusted verifier and token vault are intentionally injected interfaces, not concrete credential provisioning. A verifier implementation must independently authenticate the token signature, effective LoanHub database role, borrower profile, user state and revocation/session version or JTI. Its `BorrowerAccountEvidence` is a trusted-backend assertion, not standalone cryptographic proof. The real verification endpoint, transport security, revocation propagation, deployment configuration and approved borrower-only credential issuance still require design and controlled end-to-end validation. The new broker is not registered in the running app; all LoanHub reads and IthutePay financial writes remain disabled by default.


## Phase 41 — LoanHub signed-token and live-authority contract verifier (not deployed)

`backend/app/loanhub_identity_verifier.py` adds a backend-only adapter based on actual LoanHub repository contracts: the RS256-signed local LoanHub access token, `GET /api/v1/auth/me` and the effective database-backed authentication/session revocation behavior behind that endpoint. The adapter requires a trusted pinned LoanHub public key, a local access token with a session JTI, a successful authenticated read of the effective borrower-role account, and a separate trusted mapping from the verified LoanHub user ID to the exact borrower-profile ID and tenant. It rejects administrative or impersonation roles, expired tokens, revoked sessions as reported by LoanHub, invalid mapping, and HTTP failures.

**Critical boundary:** LoanHub's `/auth/me` does not reveal borrower-profile ID or company binding. Those must be established through a separately approved, backend-only mapping resolver—never inferred from the browser or JWT. The adapter is an injectable verifier for the Phase 40 broker, not a production-connected borrower credential vault. There is no live LoanHub URL, public key, stored borrower tokens or mapping resolver configured in Batlokoa; all customer loan routes remain default-disabled. Mock-transport tests validate the expected policy, not a production LoanHub connection. The verifier must be security-reviewed for token lifecycle and revocation before any activation.


## Phase 42 — trusted LoanHub borrower-profile ownership mapping (not activated)

The new backend-only `LoanHubBorrowerMappingResolver` executes a restricted, read-only PostgreSQL query against LoanHub's real relationship pattern: `users.id` → `borrowers.user_id` → `client_company_loan.borrower_id/company_id`. Mapping is allowed only for a previously verified LoanHub user, the server-configured target company, an active and verified borrower-role user, an active company, and an existing loan relationship for that company. The resolver accepts **no browser-supplied tenant**. It rejects unknown users, wrong companies, missing loans, suspended accounts and database failures.

The isolated PostgreSQL CI suite tests ownership, company isolation, role changes, account suspension, loan unlinking and SQL read-only enforcement. An additional mocked end-to-end test composes the real signed-JWT LoanHub identity verifier → PostgreSQL profile mapping → server-side credential broker → guarded token source → read-only LoanHub HTTP adapter; removal of the loan relationship blocks subsequent reads before the loan-list endpoint is contacted.

**Operational constraints:** Configure only through a separately reviewed bootstrap with a least-privileged, SELECT-only LoanHub database role over the necessary tables, pinned public key, secure backend-only token vault, TLS and audit logging. Applying this code does not configure credentials or connect the running Batlokoa gateway. Borrowers with no existing company loans are intentionally not mapped. It is not a general borrower affiliation claim for lending applications. The security sign-off, production role grants, mapping authorization and token lifecycle must be validated independently before any live enablement. IthutePay and loan/payment mutations remain disabled.


## Phase 43 — controlled LoanHub integration preflight (offline, never enables live access)

The standalone `backend/app/loanhub_integration_preflight.py` checks readiness **metadata** before a future supervised read-only LoanHub rollout. The explicit inputs are the approved tenant UUID, distinct HTTPS origins, a pinned LoanHub public-key file path, operator attestations that a backend token vault and borrower mapping reader are configured, proof that the mapping DB role is read-only, verified revocation handling and a currently valid security-approval reference. Missing, invalid or expired evidence fails closed, including unsafe or symlinked public-key files. The checker does not open keys, emit secrets, contact LoanHub or mutate application state. `production_enabled` is **always false**, even when all metadata is present.

Passing the preflight is **not** a security review or authority to activate anything: attestations must be independently verified and documented. A separate reviewed bootstrap, controlled credentials and real-system integration tests are still required, especially verifying lender-specific borrower access, access token lifecycle, credential storage, revocation propagation and least privilege. Standard Docker staging continues with all live loan operations and IthutePay services disabled. CI tests verify the denied/default configuration and that calling the preflight cannot turn on the application routes.

**Manual activation checklist:** verify the deployment's exact tenant, production TLS certificate and pinned LoanHub public key out of band; confirm SELECT-only LoanHub mapping DB permissions and network isolation; verify the token vault provides only actual borrower sessions; confirm revocation, expiry, cross-company denials and redacted logs; obtain reviewed security and operational approvals; validate using controlled test borrowers before enabling a separately approved bootstrap. Do not store credentials in Git or Docker image layers.


## Phase 44 — controlled LoanHub contract harness (network-free, no activation)

`backend/tests/test_phase44_controlled_loanhub_harness.py` runs Batlokoa's actual signed-JWT verifier, server-side credential broker, guarded token supplier and read-only LoanHub HTTP adapter against an in-process `httpx.MockTransport` standing in for the LoanHub `GET /api/v1/auth/me` and `GET /api/v1/loans/` endpoints. Test-only borrower identities, a disposable signing key and a controlled borrower mapping are used. There is **no outbound network call**, production credential, real user data or live financial operation.

The harness proves the expected call chain and checks that administrative roles, inactive/unverified users, centrally revoked mock sessions, token expiry, cross-tenant or cross-borrower mappings, unexpected loan response identities and upstream outages fail closed. A successful read is never treated as a cached or fabricated balance after permission loss. The GitHub gateway contract job runs these tests on pull requests.

This is **contract simulation**, not certification against a deployed LoanHub server: the fake authority is not the actual LoanHub authentication/DB implementation. The controlled real-system test environment, audited vault and SELECT-only borrower mapping credentials, pinned public key, operator approvals and verified revocation behavior are still required before a separate approved bootstrap can enable customer access. Live LoanHub access and IthutePay transactions remain disabled by default.


## Phase 45 — LoanHub-owned borrower identity proof (not activated)

The authenticated LoanHub endpoint proposed in `ithute-stak/LoanHub` PR #583
is `GET /api/v1/auth/borrower-context?company_id=<uuid>`. Its implementation
is in LoanHub itself, requiring a locally issued, revocable borrower session,
a currently active verified account, and a real loan relationship between the
borrower profile and the requested, active LoanHub company.

Batlokoa's `LoanHubRemoteBorrowerContext` sends the already verified
borrower access token to the HTTPS LoanHub origin and checks the exact
`user_id`, `company_id`, `borrower_id`, borrower role, session state
and account state from the response. The
`LoanHubIdentityVerifier` supports this **instead of** the old direct
PostgreSQL mapping callback, not alongside it; missing or ambiguous
configuration is rejected. Network redirects, errors, invalid payloads and
wrong-tenant mapping all fail closed. The original DB resolver is kept only
for backwards-compatible offline tests and remains unprovisioned.

**This is a contract implementation, not a live financial launch.** LoanHub
PR #583 needs green CI, merge, an explicitly reviewed LoanHub deployment,
and proof of real session revocation and company ownership. Batlokoa's
existing public demo must not be wired to customer credentials before
these steps, a secure token vault, security authorization and real-system
acceptance testing. No production keys, tokens, database credentials or
payment rails have been enabled by this code.
