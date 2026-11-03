# Batlokoa Finance — mobile UI specification

## Intended domain and identity
- Production public domain: https://batlokoa.co.ls (requires DNS, TLS, hosting, and deployment)
- App name: Batlokoa Finance
- Theme: deep teal #113F3C, accent mint #16A48B, light canvas #F4F8F7
- Currency: LSL (display with M prefix)
- Framework: Flutter, Material 3

## Navigation
- Mobile (<800 logical pixels): bottom navigation (Home, Loans, Wallet, Pay bills, Profile)
- Tablets/desktops (>=800): NavigationRail, extended above 1100 logical pixels
- Central content capped at 1100 logical pixels; flow forms capped at 740 pixels
- Card services use adaptive 2-column / 4-column grids
- All screens vertically scroll on small devices

## Implemented interactive UI
1. Welcome, demo sign-in and sign-up, explore demo
2. Dashboard / sample balance / quick transfers / loan summary / recent activity
3. Loans list / loan details / instalment history / loan application steps
4. Wallet and sample transactions / deposit, send, withdraw, repay forms
5. Bill categories / electricity / WASCO / airtime / data / TV / school fees
6. Transaction history
7. Profile, support, KYC, notifications and account information placeholders

## Status / limitations
- Demo only: forms do not send API requests or change money/loan balances.
- No actual OTP, identity verification, secure auth, KYC, bank or biller integration.
- No actual domain deployment or mobile app publishing.
- Replace demo data with typed API repositories and robust loading, empty, success, and error states before launch.
- Formal visual QA at phone, tablet and desktop widths remains to be done.

## Integration contracts to implement
- Ithute Auth: customer identity, OTP/MFA, verified sessions
- LoanHub: tenant-scoped borrower info, loan applications, loan schedules, agreements, repayments
- IthutePay: wallet/provider balances, payout requests, payment intents, transaction status and reconciliation
- External billers: validation, account lookup, payment creation, fulfilment, refunds and proof of payment

## Financial safety rules
- Never trust client-provided wallet balances, interest rates, fees, lending decisions or receipt status.
- Use server-side idempotency keys and audited double-entry postings.
- Do not show disbursement success before verified settlement/provider confirmation.
- No gambling funding in the initial release.

## Iteration: history details and safer preview flows

- `lib/activity_details.dart` defines clearly marked sample transaction fixtures and a dedicated transaction-detail screen.
- History rows can be opened to inspect sample reference, date, service and amount.
- Activity detail is explicitly labelled **NOT A RECEIPT**; it does not represent provider-confirmed settlement.
- `lib/payment_review.dart` remains an editable, non-transactional preview.
- Corrected a contradictory payment review test assertion.
- Added transaction-detail widget tests.

### Verification remaining

The authoring environment does not contain the Flutter or Dart SDK, so no local Flutter analyzer, unit test run or web build was executed. CI results have not been confirmed. Before calling the UI build-ready, run the repository workflow and address any analyzer, compile, rendering, or widget-test failures.

### Next UX backlog

- Responsive text scaling and landscape QA
- Distinct loading, empty, failure and retry states backed by typed API repositories
- Secure mobile onboarding flows and authentic privacy notices
- Verified digital receipts (only after production IthutePay integration)
- Accessibility labels and keyboard/screen reader passes
