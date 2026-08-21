#!/usr/bin/env bash

set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

ENVIRONMENT=""
RELEASE_ID=""
PREVIOUS_RELEASE=""
BACKUP_MANIFEST=""
BASE_URL=""
CONFIRMATION=""
PROJECT_NAME=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --environment) ENVIRONMENT="${2:-}"; shift 2 ;;
    --release-id) RELEASE_ID="${2:-}"; shift 2 ;;
    --previous-release) PREVIOUS_RELEASE="${2:-}"; shift 2 ;;
    --backup-manifest) BACKUP_MANIFEST="${2:-}"; shift 2 ;;
    --base-url) BASE_URL="${2:-}"; shift 2 ;;
    --project-name) PROJECT_NAME="${2:-}"; shift 2 ;;
    --confirm) CONFIRMATION="${2:-}"; shift 2 ;;
    *) release_die "unknown argument: $1" ;;
  esac
done

[[ "$ENVIRONMENT" = "staging" || "$ENVIRONMENT" = "production" ]] || \
  release_die "deploy environment must be staging or production"
release_validate_sha "$RELEASE_ID"
release_validate_sha "$PREVIOUS_RELEASE"
[[ "$RELEASE_ID" != "$PREVIOUS_RELEASE" ]] || \
  release_die "release id and previous release must be different"
release_require_clean_sha "$RELEASE_ID"
release_require_env_file
release_verify_backup_manifest "$BACKUP_MANIFEST" "$PREVIOUS_RELEASE"
[[ "$BASE_URL" =~ ^https://[^/]+$ ]] || release_die "invalid HTTPS base URL"
[[ "$PROJECT_NAME" =~ ^[a-z0-9][a-z0-9_-]+$ ]] || release_die "explicit safe --project-name is required"
[[ "$CONFIRMATION" = "DEPLOY ${ENVIRONMENT} ${RELEASE_ID}" ]] || \
  release_die "confirmation must exactly match: DEPLOY ${ENVIRONMENT} ${RELEASE_ID}"

export IMAGE_TAG="$RELEASE_ID"
export RUN_MIGRATIONS=0
export DEPLOY_PROJECT_NAME="$PROJECT_NAME"

release_assert_image "mudaroba-backend:${RELEASE_ID}" "$RELEASE_ID"
release_assert_image "mudaroba-frontend:${RELEASE_ID}" "$RELEASE_ID"
release_assert_image "mudaroba-backend:${PREVIOUS_RELEASE}" "$PREVIOUS_RELEASE"
release_assert_image "mudaroba-frontend:${PREVIOUS_RELEASE}" "$PREVIOUS_RELEASE"

release_log "printing migration plan"
release_compose_prod --profile ops run --rm --no-deps migrate migrate --plan
release_log "entering a controlled maintenance window before schema changes"
release_compose_prod stop \
  nginx frontend backend celeryworker celery_ai celery_recsys celerybeat
release_log "ensuring existing state services are running without recreating containers or volumes"
release_compose_prod up -d --no-recreate postgres redis qdrant
release_log "applying committed migrations exactly once"
release_compose_prod --profile ops run --rm --no-deps migrate migrate --noinput
release_log "starting one consistent release without rebuilding or automatic migrations"
release_compose_prod up -d --no-build --no-deps --wait --wait-timeout 180 \
  backend frontend celeryworker celery_ai celery_recsys celerybeat nginx
release_compose_prod ps

"${RELEASE_SCRIPT_DIR}/postdeploy-smoke.sh" --base-url "$BASE_URL"
release_log "deploy completed: ${ENVIRONMENT}:${RELEASE_ID}"
release_log "keep previous images and backups until the observation window closes"
