# Batlokoa employee sign-in: account verification and pilot acceptance

## Verified current blockers (2026-11-22)

- LoanHub has two **active** memberships for the Batlokoa Financial Services company.
- Both associated users are **unverified** in LoanHub (`users.is_verified = false`).
- The Batlokoa gateway correctly checks `is_active`, `is_verified`, `must_change_password`, current token signature/session, active Batlokoa membership and assigned branch before authorizing a session.
- The read-only browser session route is enabled on the Batlokoa deployment; an anonymous request receives HTTP 401, not an authenticated identity.
- Neither employee can be certified as successfully signed in until actual verification and a real user acceptance test occur.

## Authorized LoanHub action (not automated)

1. Have a **LoanHub platform administrator** verify the employee's real identity, employment and intended Batlokoa company/branch assignment using the organization's normal identity evidence.
2. In the authorized LoanHub user-management workflow, set `is_verified` to `true` for the **specific approved user**, using the administrator-only `PUT /api/v1/auth/users/{user_id}` API with only the `is_verified` update field, or the equivalent reviewed administrative UI.
3. Confirm the correct branch membership, employee role, account active state, and whether password changes or MFA are required. **Never** bypass account verification with raw SQL, borrowed credentials or fake login.
4. Test with the **employee personally entering their own credentials** at `https://batlokoa.co.ls` → Employee portal. Do not paste credentials, OTPs or recovery codes into chat, logs or source code.
5. Confirm a verified session, company scope, authorized branch, directory access, and secure logout; test denial of unverified/wrong-company users.
6. Preserve the restricted pilot's 10-minute in-memory session lifetime. The pilot is **not** a hardened multi-worker production authentication system. Refresh sessions only through reauthentication.
7. Financial writes, new client creation, loan approvals and payments remain disabled.

## Failure handling

- HTTP 401 during sign-in: invalid credentials, invalid/unverified staff membership, expired token or additional verification; preserve generic user-facing errors.
- HTTP 403: same-origin/CSRF/branch authorization rejected; never retry by removing the controls.
- HTTP 503: integration or upstream unavailable; inspect sanitized gateway health and configuration without exposing tokens.
- If company or branch assignment is uncertain, stop and have the administrator correct the source of truth in LoanHub.
