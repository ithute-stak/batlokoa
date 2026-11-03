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
