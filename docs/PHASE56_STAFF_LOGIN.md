# Phase 56 — opt-in Batlokoa employee sign-in (staging only)

## Implemented
- `POST /api/v1/staff/login` accepts LoanHub's existing phone/password
  credentials via a same-origin HTTPS Batlokoa backend. The backend relays
  credentials to LoanHub's `POST /api/v1/auth/login`, obtains an access token,
  verifies live company/branch membership using `GET /api/v1/auth/me`, and
  **never returns the LoanHub access token to Flutter**.
- The browser receives a short-lived Secure, HttpOnly, SameSite=Strict opaque
  Batlokoa session cookie (at most ten minutes), plus a separate CSRF cookie.
- `GET /api/v1/staff/session` re-verifies active LoanHub membership and
  session revocation on every request before showing staff role and branches.
- `POST /api/v1/staff/logout` requires the exact public origin and CSRF
  header/cookie proof, and revokes the Batlokoa volatile session.
- Strict HTTPS origins, bounded HTTP response sizes, network timeouts and no
  redirects. No borrower impersonation and no staff financial writes.

## Deployment guard
All staff routes default to **HTTP 503**. An operator must deliberately set
`app.state.staff_login_config` to a reviewed `StaffLoginConfig` with:
- approved same-origin public HTTPS URL;
- approved LoanHub HTTPS origin;
- pinned real LoanHub RS256 verification public key;
- known Batlokoa company UUID; and
- a `StagingStaffSessionStore` **for a single-process staging instance only**.

No real key, ID, password or customer data is committed. No production
configuration is provided. If LoanHub requires MFA for an employee, its
existing enforcement remains authoritative; this phase does not introduce
or bypass OTP policies. The login form currently supports only phone/password,
so staff whose accounts require an additional factor cannot complete login
through this integration yet.

## Production blockers
This in-memory store holds active LoanHub access tokens in process RAM. It has
no shared distributed invalidation, durable encrypted credential vault, process
restart continuity, rotation or access-token refresh; it is **not suitable for
multiworker/public production**. Restrict staging access and keep it single
worker until a security-reviewed distributed session design is available.
LoanHub logout is not called: the Batlokoa local session is revoked, while
LoanHub upstream access token remains valid until its own expiration or
independent revocation. Never claim upstream logout.

A Flutter staff login form and dashboard, active branch selection,
secure client list, client creation, loan request and offer adapters remain
future work. LoanHub remains authoritative for approvals and financial writes.
