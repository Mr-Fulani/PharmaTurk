#!/usr/bin/env bash

set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

RELEASE_ID=""
SMOKE_PORT_VALUE="18080"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --release-id) RELEASE_ID="${2:-}"; shift 2 ;;
    --port) SMOKE_PORT_VALUE="${2:-}"; shift 2 ;;
    *) release_die "unknown argument: $1" ;;
  esac
done

[[ -n "$RELEASE_ID" ]] || release_die "--release-id is required"
release_validate_tag "$RELEASE_ID"
[[ "$SMOKE_PORT_VALUE" =~ ^[0-9]{4,5}$ ]] || release_die "port must contain 4-5 digits"
(( SMOKE_PORT_VALUE >= 1024 && SMOKE_PORT_VALUE <= 65535 )) || release_die "port is out of range"
release_require_command docker
release_require_command curl
release_require_env_file
release_assert_image "mudaroba-backend:${RELEASE_ID}" "$RELEASE_ID"
release_assert_image "mudaroba-frontend:${RELEASE_ID}" "$RELEASE_ID"

# Use this script's PID, not its parent's. CI/agent wrappers can reuse one
# parent process for multiple invocations; PPID would then make independent
# smoke runs share (and tear down) the same Compose project.
SMOKE_SUFFIX="${RELEASE_ID:0:12}-$$"
DEPLOY_PROJECT_NAME="mudaroba-smoke-${SMOKE_SUFFIX}"
[[ "$DEPLOY_PROJECT_NAME" =~ ^mudaroba-smoke-[a-z0-9._-]+$ ]] || release_die "unsafe smoke project name"
export IMAGE_TAG="$RELEASE_ID"
export RUN_MIGRATIONS=0
export SMOKE_PORT="$SMOKE_PORT_VALUE"

smoke_compose() {
  docker compose \
    --project-name "$DEPLOY_PROJECT_NAME" \
    -f "$RELEASE_COMPOSE_BASE" \
    -f "$RELEASE_COMPOSE_SMOKE" \
    "$@"
}

headers_file=""
cleanup() {
  local status=$?
  if [[ "$status" -ne 0 ]]; then
    release_log "smoke failed; collecting isolated service diagnostics"
    smoke_compose ps || true
    smoke_compose logs --tail=120 postgres redis qdrant backend frontend nginx || true
  fi
  if [[ -n "$headers_file" ]]; then
    rm -f "$headers_file"
  fi
  release_log "removing only isolated project ${DEPLOY_PROJECT_NAME}"
  smoke_compose down --volumes --remove-orphans >/dev/null 2>&1 || true
  return "$status"
}
trap cleanup EXIT

release_log "starting isolated state services on project ${DEPLOY_PROJECT_NAME}"
smoke_compose up -d postgres redis qdrant
release_log "applying migrations once through the ops service"
smoke_compose --profile ops run --rm migrate
release_log "starting application services without automatic migrations"
smoke_compose up -d --no-build backend frontend nginx

LIVE_URL="http://127.0.0.1:${SMOKE_PORT_VALUE}/api/live/"
HEALTH_URL="http://127.0.0.1:${SMOKE_PORT_VALUE}/api/health/"
CURL_HEADERS=(-H "Host: mudaroba.com" -H "X-Forwarded-Proto: https")

ready=0
for _ in $(seq 1 60); do
  if curl --silent --fail --connect-timeout 2 --max-time 5 \
      "${CURL_HEADERS[@]}" "$HEALTH_URL" >/dev/null; then
    ready=1
    break
  fi
  sleep 2
done
[[ "$ready" = "1" ]] || {
  smoke_compose ps
  smoke_compose logs --tail=120 backend frontend nginx
  release_die "isolated readiness did not become healthy"
}

release_log "checking liveness, readiness, canonical host, and response headers"
curl --silent --show-error --fail --connect-timeout 5 --max-time 15 \
  "${CURL_HEADERS[@]}" "$LIVE_URL" >/dev/null
curl --silent --show-error --fail --connect-timeout 5 --max-time 15 \
  "${CURL_HEADERS[@]}" "$HEALTH_URL" >/dev/null

headers_file="$(mktemp)"
curl --silent --show-error --fail --connect-timeout 5 --max-time 15 \
  -D "$headers_file" -o /dev/null "${CURL_HEADERS[@]}" \
  "http://127.0.0.1:${SMOKE_PORT_VALUE}/"
grep -qi '^Strict-Transport-Security: max-age=31536000; includeSubDomains' "$headers_file" || \
  release_die "HSTS header is missing on simulated HTTPS ingress"
if grep -qi '^X-Powered-By:' "$headers_file"; then
  release_die "X-Powered-By is exposed"
fi

redirect_location="$(curl --silent --show-error --connect-timeout 5 --max-time 15 \
  -o /dev/null -w '%{redirect_url}' -H 'Host: www.mudaroba.com' \
  -H 'X-Forwarded-Proto: https' "http://127.0.0.1:${SMOKE_PORT_VALUE}/probe")"
[[ "$redirect_location" = "https://mudaroba.com/probe" ]] || \
  release_die "www canonical redirect is incorrect"

release_log "isolated smoke passed for ${RELEASE_ID}"
