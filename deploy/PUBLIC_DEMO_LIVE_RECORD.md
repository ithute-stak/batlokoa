# Public demo launch record — 2026-11-05

Batlokoa Financial Services' **demo only** was deployed to `loanhub-prod`
using the immutable images with SHA tag
`demo-6e2e436487d44a861242b11d39f31f2f0ffa8779`.
No real LoanHub customer account, loan application, borrower authentication,
IthutePay payment, or transfer is enabled.

## Source of truth and runtime state

- Docker Compose: `/opt/batlokoa-demo/compose.vps.demo.yml`,
  version controlled as `compose.vps.demo.yml`. Both services are on their
  own default network plus existing external `public-edge`.
- Existing Caddy: `ithute-caddy-1`; its configuration imports
  `/data/product-routes/*.caddy`.
- Batlokoa route: `/data/product-routes/batlokoa.caddy` inside Caddy, stored
  in Docker volume `ithute_ithute_caddy_data`. The reviewed route is stored
  here as `deploy/batlokoa.public-demo.caddy`.
- Local loopback ports: web 18088, gateway 18089. Do not bind publicly.
- Domain DNS: PowerDNS zone `batlokoa.co.ls`, A records for apex and
  `www` pointing at `204.12.205.224`; existing MX, SPF, DKIM, DMARC
  and other mail records preserved. DNS zone is stored in PowerDNS's existing
  persistent volume; no new zone file was created in Git.
- TLS: valid Let's Encrypt certificates obtained by Caddy for apex and
  `www` on 2026-11-05. HTTPS automatic renewal remains Caddy's responsibility.

## Verified smoke tests

HTTPS `GET /` returned 200, `GET /healthz` reported ok,
`GET /api/v1/capabilities` returned `integration_disabled` and
all financial capability values false, and `www` redirected to the apex.
Customer loan read, login/session, wallet, and POST payment intent and loan
application endpoints returned 503 as expected. Both Docker containers
reported healthy after applying the version-controlled external network.

## Operational safety

This is not a verified financial production release. Ensure the demo's
sample-data limitation is clear to all testers; do not submit real personal
or financial details. The route includes `X-Batlokoa-Mode: demo` and a
noindex header, but these alone are not a visible user-facing disclaimer.
Before offering a true financial service, obtain explicit approval of
LoanHub borrower identity and tenancy, real authentication, IthutePay
authorization and reconciliation, audit, incident response and backups.

For rollback, remove only `batlokoa.caddy` from the separate product route
directory, validate the full Caddy config, then perform a Caddy reload.
Alternatively roll back only the isolated Batlokoa Compose project to its
previous known-good immutable tags. Do not stop any other Compose stack or
remove shared Caddy, PowerDNS, LoanHub or IthutePay volumes.
