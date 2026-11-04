# Batlokoa VPS deployment — safe demo only

This deployment serves the Flutter web demonstration and its fail-closed
FastAPI gateway. **It is NOT a live financial application**: sample balances
are shown, LoanHub customer reads and IthutePay financial actions stay disabled.

## Preconditions

- The existing VPS administrator must verify free loopback ports `18088`
  and `18089` and verify that the existing edge reverse proxy owns the
  intended hostname. Do **not** overwrite LoanHub or IthutePay proxy files.
- Existing Docker Compose projects, Docker volumes and production databases
  must be preserved. This Compose project has unique `batlokoa-demo` naming,
  no data volumes and no database services.
- Log in to GitHub Container Registry with a PAT granting only the package
  read permission appropriate to the images (if they are private).
- Confirm DNS and the TLS certificate for `batlokoa.co.ls` separately.
- Do not place credentials in Docker images, git or application source.

## Build images in GitHub Actions

In GitHub Actions, manually run
`Publish Batlokoa disabled-demo Docker images` on the audited main commit.
This builds and tests Flutter, builds the web and gateway Docker images, and
publishes immutable `demo-<full-commit-sha>` tags to GHCR. This workflow
does not deploy the VPS or enable customer integrations. Check that BOTH
packages were published successfully.

## On VPS: verify the environment before changing anything

The following commands are for an administrator using an existing authorized
VPS shell after the registry images and Compose file are available:

```bash
sudo docker compose ls
sudo docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
sudo ss -ltnp | grep -E ':(80|443|18088|18089)\\b' || true
sudo nginx -t
```

Check that the ports are free and that an existing proxy will not route
sensitive traffic to a demonstration service. Back up the existing edge
configuration BEFORE considering hostname changes. Do not stop or delete
any other Compose projects.

## Pull and run only the published immutable images

Place `compose.vps.demo.yml` into a dedicated `~/batlokoa-demo` directory,
and replace `<verified-full-commit-sha>` with the exact SHA on the successful
GHCR build. Use an image tag for which both web and gateway images exist.

```bash
cd ~/batlokoa-demo
export BATLOKOA_RELEASE_SHA=<verified-full-commit-sha>
sudo -E docker compose -f compose.vps.demo.yml config --quiet
sudo -E docker compose -f compose.vps.demo.yml pull
sudo -E docker compose -f compose.vps.demo.yml up -d --no-build
sudo -E docker compose -f compose.vps.demo.yml ps
curl --fail --silent http://127.0.0.1:18088/healthz
curl --fail --silent http://127.0.0.1:18089/healthz
curl --fail --silent http://127.0.0.1:18089/api/v1/capabilities
```

The capabilities response must have `mode=integration_disabled`, with every
financial capability `false`. Verify the API's loan/session/payment routes
return disabled statuses before publishing the hostname. If this fails, do not
expose the service.

## Reverse proxy and SSL

After determining whether existing Nginx, Traefik or Caddy owns port 443,
add a *separate, reviewed* hostname-only routing configuration:
`/api/` to loopback `127.0.0.1:18089`, and web `/` to loopback
`127.0.0.1:18088`. The configuration must use the actual TLS certificate
for `batlokoa.co.ls`, preserve same-origin requests, and not overwrite
any LoanHub or IthutePay routes. Always validate and reload the edge safely.

Do not expose the demo externally before the operator signs off on the
prominent demo/sample-data disclosures and on whether public access is
appropriate. This does not activate customer authentication or payments.

## Rollback

Record the previously deployed image SHA. To return to it, set
`BATLOKOA_RELEASE_SHA` back to that SHA and re-run
`docker compose -f compose.vps.demo.yml up -d --no-build`.
Rollback of a hostname change must be handled through the existing edge,
without removing persistent volumes belonging to LoanHub or IthutePay.
