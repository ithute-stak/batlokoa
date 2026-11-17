# Phase 55 — Verified LoanHub employee context (read-only)

LoanHub source verification, 2026-11-17:
- `POST /api/v1/auth/login` authenticates `phone` and `password`, optionally
  applying LoanHub's existing second-factor policy. Batlokoa must not bypass
  any account security enforced by LoanHub.
- `GET /api/v1/auth/me` resolves the live session, active user account and
  active company staff memberships, including company, branch and role.
- LoanHub's access token is an RS256 access JWT with `user_id`,
  `session_jti` and expiry. LoanHub itself validates refresh-session
  revocation during `/auth/me`.

This PR adds a backend-only verifier that validates the access token signature,
rejects impersonation, calls LoanHub's authoritative `/auth/me`, and binds an
active, verified user to **one** active Batlokoa company membership. Branch IDs
and permissions are never trusted from Flutter. Negative tests use mock HTTP.

It does **not** yet implement end-user login, browser session persistence,
refresh, route registration or staff client writes. Do not forward LoanHub
access tokens to browser storage or log token payloads.

## Next
Implement a separately reviewed same-origin HTTPS BFF login using LoanHub's
`/auth/login`; never store passwords. An operator must pin the Batlokoa
company UUID, trusted LoanHub verification key and approved origin, and provide
a secure session store. Explicitly block loan writes while session lifecycle,
logout/revocation propagation, CSRF and activity auditing remain incomplete.
