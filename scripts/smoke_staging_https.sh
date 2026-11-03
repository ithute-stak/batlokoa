#!/usr/bin/env bash
# Local CI may use its own disposable self-signed certificate.
# The --insecure flag below MUST NOT be reused in production clients.
set -euo pipefail
PORT="${BATLOKOA_STAGING_TLS_PORT:-18443}"
ORIGIN="https://127.0.0.1:${PORT}"
for attempt in $(seq 1 40); do
  if curl --insecure --silent --fail --max-time 2 "${ORIGIN}/healthz" | grep -qx ok; then
    break
  fi
  if [ "$attempt" -eq 40 ]; then
    echo "HTTPS staging edge failed health check" >&2
    docker compose -f compose.staging.https.yml ps >&2 || true
    docker compose -f compose.staging.https.yml logs --tail=100 batlokoa-edge batlokoa-web-preview >&2 || true
    exit 1
  fi
  sleep 1
done
# Web Nginx can become healthy before the API gateway has started.
# Require the API to answer through the HTTPS edge rather than accepting 502.
for attempt in $(seq 1 40); do
  if curl --insecure --silent --fail --max-time 2 "${ORIGIN}/api/v1/capabilities" | grep -q '"integration_disabled"'; then
    break
  fi
  if [ "$attempt" -eq 40 ]; then
    echo "HTTPS gateway failed readiness check" >&2
    docker compose -f compose.staging.https.yml ps >&2 || true
    docker compose -f compose.staging.https.yml logs --tail=80 batlokoa-edge batlokoa-gateway-preview >&2 || true
    exit 1
  fi
  sleep 1
done
headers="$(curl --insecure --silent --show-error --dump-header - --output /dev/null "${ORIGIN}/")"
grep -qi '^x-content-type-options: nosniff' <<< "$headers"
grep -qi '^x-frame-options: DENY' <<< "$headers"
for route in /api/v1/auth/login /api/v1/auth/session /api/v1/me/loans /api/v1/me/wallet; do
  result="$(curl --insecure --silent --output /dev/null --write-out '%{http_code}' "${ORIGIN}${route}")"
  test "$result" = 503 || { echo "FAIL: ${route} returned ${result}" >&2; exit 1; }
done
for route in /api/v1/auth/logout /api/v1/payments/intents /api/v1/loans/applications; do
  result="$(curl --insecure --silent --request POST --output /dev/null --write-out '%{http_code}' "${ORIGIN}${route}")"
  test "$result" = 503 || { echo "FAIL: ${route} returned ${result}" >&2; exit 1; }
done
echo "HTTPS edge safe-default acceptance checks passed"
