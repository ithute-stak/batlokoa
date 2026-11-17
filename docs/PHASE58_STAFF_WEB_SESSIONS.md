# Phase 58 — Browser employee session and logout connection

- Flutter employee entry now selects a same-origin HTTPS BrowserClient only on
  web, with browser-managed cookie credentials. Native app builds default to
  `DisabledStaffGateway` until an OS-protected cookie bridge is reviewed.
- The web client never reads the HttpOnly session cookie and never persists
  LoanHub tokens. It may read only the deliberately non-HttpOnly CSRF proof.
- `POST /api/v1/staff/login` authenticates in LoanHub through Batlokoa's BFF;
  the UI then calls `GET /api/v1/staff/session` to independently revalidate
  current employee membership and branch.
- `POST /api/v1/staff/logout` sends a same-origin CSRF header and clears the
  view only after a verified HTTP 200 / `logged_out: true` response. The
  browser itself supplies the Origin header.
- HTTP adapter tests cover login, verified session, logout and missing CSRF.

## Staging-only, not production-ready
The Batlokoa BFF (Phase 56) continues to be disabled by default. Its
single-process volatile token store is not suitable for production or a
multiworker deployment. Real employee credentials should only be entered
after an approved staging operator enables a secure origin, pinned LoanHub
verifier, company membership and session configuration. LoanHub's MFA
requirements remain effective; this browser interface does not yet support OTP.

Further work: distributed session lifecycle, server-side staff name / company
name / branch name resolution, full mobile secure cookie support, approved
client read and write operations, and independent security acceptance.
