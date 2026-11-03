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
