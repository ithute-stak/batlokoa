# Batlokoa Flutter Web deployment

This repository contains **demo-only** financial screens. Do **not** expose a live financial service or collect real customer information until LoanHub, IthutePay, authentication, compliance, and operational reviews are complete.

## Build and package

Run in an isolated CI job or developer workstation with Flutter installed:

```bash
flutter create . --platforms=android,web --no-pub
flutter pub get
flutter analyze --no-fatal-infos
flutter test
flutter build web --release
docker build -f Dockerfile.web -t batlokoa-web:preview .
docker compose -f compose.web.yml up -d --build
curl --fail http://127.0.0.1:8088/healthz
```

The container listens on port 8080 and Docker Compose binds only to 127.0.0.1:8088. Configure an external, TLS-enabled reverse proxy routing **batlokoa.co.ls** to that port. Do not publish the port directly to the public internet without HTTPS. DNS, TLS certificates, proxies, secrets, and a real deployment target are **not** provisioned by this repository.

## Security checklist before live traffic

- Only publish demo preview to an explicitly authorised test audience.
- Configure reverse-proxy TLS, HSTS once HTTPS is verified, access logging and rate limiting.
- Review Content Security Policy for the exact Flutter renderer/assets. Do not apply a CSP that breaks engine initialization.
- Replace demo authentication and balances with verified server-side APIs and sessions.
- Verify LoanHub tenant isolation and IthutePay settlement and webhook integrity.
- Review accessibility and browser compatibility at narrow and wide viewports.
- Plan and test zero-downtime updates and rollback.
- Treat the /healthz endpoint as liveness only, not dependency or financial readiness.

## CI

The GitHub Actions workflow produces a downloadable **batlokoa-web-preview** artifact only after analyzer, widget tests and release build pass. A successful build does not imply production approval.
