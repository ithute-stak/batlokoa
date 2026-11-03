#!/usr/bin/env bash
# Test ONLY the disabled local staging preview. This does not configure live Auth.
set -euo pipefail
WEB_PORT="${BATLOKOA_STAGING_WEB_PORT:-18088}"
API_PORT="${BATLOKOA_STAGING_API_PORT:-18089}"
WEB="http://127.0.0.1:${WEB_PORT}"
API="http://127.0.0.1:${API_PORT}"

for attempt in $(seq 1 40); do
  if curl --silent --fail --max-time 2 "${API}/healthz" | grep -q '"status":"ok"'; then
    break
  fi
  if [ "${attempt}" -eq 40 ]; then
    echo "Gateway failed to start" >&2
    exit 1
  fi
  sleep 1
done

curl --silent --fail --max-time 5 "${WEB}/healthz" | grep -qx ok
capabilities="$(curl --silent --fail --max-time 5 "${API}/api/v1/capabilities")"
python -c 'import json,sys; c=json.loads(sys.argv[1]); assert c["mode"]=="integration_disabled"; assert c["capabilities"] and not any(c["capabilities"].values())' "$capabilities"

for route in /api/v1/auth/login /api/v1/auth/session /api/v1/me/loans /api/v1/me/wallet; do
  status="$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 5 "${API}${route}")"
  test "$status" = 503 || { echo "${route} unexpectedly returned ${status}" >&2; exit 1; }
done

for route in /api/v1/payments/intents /api/v1/loans/applications /api/v1/auth/logout; do
  status="$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 5 -X POST "${API}${route}")"
  test "$status" = 503 || { echo "${route} unexpectedly returned ${status}" >&2; exit 1; }
done
echo "Staging preview checks passed: all authentication and financial operations remain disabled."
