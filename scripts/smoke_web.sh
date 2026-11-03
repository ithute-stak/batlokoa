#!/usr/bin/env bash
set -euxo pipefail

PORT="${BATLOKOA_SMOKE_PORT:-18088}"
CONTAINER="batlokoa-smoke-$$"
IMAGE="${BATLOKOA_SMOKE_IMAGE:-batlokoa-web:ci}"

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker run -d --name "$CONTAINER" -p "127.0.0.1:${PORT}:8080" "$IMAGE" >/dev/null

BASE="http://127.0.0.1:${PORT}"
ready=0
for attempt in $(seq 1 30); do
  if curl --silent --show-error --fail "$BASE/healthz" 2>/dev/null | grep -qx 'ok'; then
    ready=1
    break
  fi
  sleep 1
done
if [ "$ready" != 1 ]; then
  docker logs "$CONTAINER" || true
  echo "Container did not become healthy" >&2
  exit 1
fi

index="$(curl --silent --show-error --fail "$BASE/")"
grep -q '<title>Batlokoa Finance</title>' <<< "$index"
grep -q 'flutter_bootstrap.js' <<< "$index"
curl --silent --show-error --fail -o /dev/null "$BASE/flutter_bootstrap.js"
curl --silent --show-error --fail -o /dev/null "$BASE/main.dart.js"

# Browser refreshes and client-side routes must return the app shell.
spa="$(curl --silent --show-error --fail "$BASE/demo/activity")"
grep -q '<title>Batlokoa Finance</title>' <<< "$spa"

# Confirm application resources have security headers.
headers="$(curl --silent --show-error --fail -D - -o /dev/null "$BASE/")"
grep -qi 'x-content-type-options: nosniff' <<< "$headers"
grep -qi 'x-frame-options: DENY' <<< "$headers"

echo "Batlokoa static web container smoke checks passed"
