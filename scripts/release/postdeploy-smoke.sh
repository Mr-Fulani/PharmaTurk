#!/usr/bin/env bash

set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

BASE_URL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url) BASE_URL="${2:-}"; shift 2 ;;
    *) release_die "unknown argument: $1" ;;
  esac
done

[[ "$BASE_URL" =~ ^https://[^/]+$ ]] || \
  release_die "--base-url must be an HTTPS origin without a path or trailing slash"
release_require_command curl

headers_file="$(mktemp)"
trap 'rm -f "$headers_file"' EXIT

release_log "checking public liveness and readiness"
curl --silent --show-error --fail --connect-timeout 5 --max-time 15 \
  "${BASE_URL}/api/live/" >/dev/null
curl --silent --show-error --fail --connect-timeout 5 --max-time 15 \
  "${BASE_URL}/api/health/" >/dev/null

release_log "checking public security headers"
curl --silent --show-error --fail --connect-timeout 5 --max-time 15 \
  -D "$headers_file" -o /dev/null "${BASE_URL}/"
grep -qi '^Strict-Transport-Security:' "$headers_file" || release_die "HSTS header is missing"
grep -qi '^X-Content-Type-Options: nosniff' "$headers_file" || \
  release_die "X-Content-Type-Options header is missing"
if grep -qi '^X-Powered-By:' "$headers_file"; then
  release_die "X-Powered-By is exposed"
fi

release_log "public smoke passed for ${BASE_URL}"
