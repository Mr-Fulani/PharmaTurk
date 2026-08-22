#!/usr/bin/env bash

set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

ENVIRONMENT=""
RELEASE_ID=""
ALLOW_DIRTY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --environment) ENVIRONMENT="${2:-}"; shift 2 ;;
    --release-id) RELEASE_ID="${2:-}"; shift 2 ;;
    --allow-dirty) ALLOW_DIRTY=1; shift ;;
    *) release_die "unknown argument: $1" ;;
  esac
done

[[ -n "$ENVIRONMENT" ]] || release_die "--environment is required"
[[ -n "$RELEASE_ID" ]] || release_die "--release-id is required"
release_validate_environment "$ENVIRONMENT"
release_validate_tag "$RELEASE_ID"
release_require_command docker
release_require_command git
release_require_env_file

if [[ "$ENVIRONMENT" = "local" ]]; then
  if [[ "$ALLOW_DIRTY" != "1" ]]; then
    [[ -z "$(git -C "$RELEASE_REPO_ROOT" status --porcelain)" ]] || \
      release_die "local tree is dirty; use --allow-dirty only for non-deployable testing"
  fi
else
  [[ "$ALLOW_DIRTY" = "0" ]] || release_die "--allow-dirty is forbidden outside local testing"
  release_require_clean_sha "$RELEASE_ID"
fi

export IMAGE_TAG="$RELEASE_ID"
export DEPLOY_PROJECT_NAME="mudaroba-predeploy-${RELEASE_ID:0:12}-$PPID"

test_compose() {
  docker compose \
    --project-name "$DEPLOY_PROJECT_NAME" \
    -f "$RELEASE_COMPOSE_BASE" \
    -f "${RELEASE_REPO_ROOT}/docker-compose.test.yml" \
    "$@"
}

cleanup_test_services() {
  release_log "removing only isolated test project ${DEPLOY_PROJECT_NAME}"
  test_compose down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup_test_services EXIT

release_log "checking patch whitespace and Compose contracts"
git -C "$RELEASE_REPO_ROOT" diff --check
docker compose -f "$RELEASE_COMPOSE_BASE" -f "${RELEASE_REPO_ROOT}/docker-compose.override.yml" config --quiet
release_compose_prod config --quiet

if command -v sha256sum >/dev/null 2>&1; then
  DEPENDENCY_LOCK_HASH="$(sha256sum \
    "${RELEASE_REPO_ROOT}/backend/pyproject.toml" \
    "${RELEASE_REPO_ROOT}/backend/poetry.lock" | sha256sum | awk '{print $1}')"
else
  DEPENDENCY_LOCK_HASH="$(shasum -a 256 \
    "${RELEASE_REPO_ROOT}/backend/pyproject.toml" \
    "${RELEASE_REPO_ROOT}/backend/poetry.lock" | shasum -a 256 | awk '{print $1}')"
fi
export DEPENDENCY_LOCK_HASH

release_log "building immutable application and test images"
release_compose_prod build backend frontend
test_compose --profile test build backend_tests
release_assert_image "mudaroba-backend:${RELEASE_ID}" "$RELEASE_ID"
release_assert_image "mudaroba-frontend:${RELEASE_ID}" "$RELEASE_ID"
release_assert_image "mudaroba-backend-test:${RELEASE_ID}" "$RELEASE_ID"

release_log "starting isolated backend test dependencies"
test_compose up -d --wait postgres redis qdrant

release_log "running backend release gates against isolated state services"
test_compose --profile test run --rm backend_tests check --lock
test_compose --profile test run --rm backend_tests run python manage.py check
test_compose --profile test run --rm backend_tests run python manage.py makemigrations --check --dry-run
test_compose --profile test run --rm backend_tests run pytest -q

release_log "running frontend release gates"
docker run --rm \
  --mount "type=bind,src=${RELEASE_REPO_ROOT}/frontend,dst=/src,readonly" \
  --mount "type=volume,dst=/app" \
  --workdir /app \
  node:22.23.2-bookworm-slim \
  sh -ec '
    tar \
      --exclude=./node_modules \
      --exclude=./.next \
      --exclude=./tsconfig.tsbuildinfo \
      -C /src -cf - . | tar -C /app -xf -
    npm ci --include=dev
    npm audit --omit=dev --audit-level=high
    npm run lint
    npx tsc --noEmit --incremental false
    npm test
    npm run build
  '

release_log "predeploy passed for ${ENVIRONMENT}:${RELEASE_ID}"
if [[ "$ALLOW_DIRTY" = "1" ]]; then
  release_log "this was a dirty-tree audit build and must not be deployed"
fi
