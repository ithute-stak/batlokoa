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
