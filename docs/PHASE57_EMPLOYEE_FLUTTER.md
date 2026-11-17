# Phase 57 — Batlokoa employee Flutter entry and dashboard

This phase adds a **separate employee portal** from the existing customer demo:
- Employee entry point on welcome screen (phone/password, never demo sign-in).
- Session-driven role and assigned branch details, obtained only from the BFF.
- Locked client registration, loan application, client search, and offer actions
  until approved service adapters are ready.
- Login/session/logout view-model through a `StaffGateway` interface, with
  network-free widget tests for login, logout and disabled states.

## Critical limitation
The default `StaffPortal` uses `DisabledStaffGateway`: the UI **cannot
authenticate a real LoanHub employee** until an operator wires a reviewed
environment-specific gateway. `SameOriginStaffGateway` is only a preliminary
HTTP client contract. It does not yet complete platform-specific cookie and
CSRF handling, and logout deliberately fails closed rather than claiming to
revoke an upstream session. It must NOT be wired into production.

Phase 56's in-memory backend login also remains staging-only and disabled
without trusted configuration; it cannot serve production multiworker sessions.
The app has not been deployed, and no loan or client modifications are live.

## Next steps
1. Complete the HTTPS same-origin browser/mobile cookie and CSRF client.
2. Design distributed server-side staff sessions, safe logout and MFA support.
3. Resolve company **name**, employee display **name**, and authorized branch
   **names** from trusted LoanHub sources (rather than displaying internal IDs).
4. Enable employee sign-in on approved staging and prove branch isolation.
5. Build backend-only client list and registration adapter using LoanHub's
   current company-client schema; test duplicate / legacy national ID handling.
6. Build staff-originated application and loan-offer adapters separately.
