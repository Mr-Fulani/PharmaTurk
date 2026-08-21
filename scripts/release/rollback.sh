#!/usr/bin/env bash

set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

ENVIRONMENT=""
TARGET_RELEASE=""
BASE_URL=""
CONFIRMATION=""
PROJECT_NAME=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --environment) ENVIRONMENT="${2:-}"; shift 2 ;;
    --target-release) TARGET_RELEASE="${2:-}"; shift 2 ;;
    --base-url) BASE_URL="${2:-}"; shift 2 ;;
    --project-name) PROJECT_NAME="${2:-}"; shift 2 ;;
    --confirm) CONFIRMATION="${2:-}"; shift 2 ;;
    *) release_die "unknown argument: $1" ;;
  esac
done

[[ "$ENVIRONMENT" = "staging" || "$ENVIRONMENT" = "production" ]] || \
  release_die "rollback environment must be staging or production"
release_validate_sha "$TARGET_RELEASE"
[[ "$BASE_URL" =~ ^https://[^/]+$ ]] || release_die "invalid HTTPS base URL"
[[ "$PROJECT_NAME" =~ ^[a-z0-9][a-z0-9_-]+$ ]] || release_die "explicit safe --project-name is required"
[[ "$CONFIRMATION" = "ROLLBACK ${ENVIRONMENT} ${TARGET_RELEASE}" ]] || \
  release_die "confirmation must exactly match: ROLLBACK ${ENVIRONMENT} ${TARGET_RELEASE}"

export IMAGE_TAG="$TARGET_RELEASE"
export RUN_MIGRATIONS=0
export DEPLOY_PROJECT_NAME="$PROJECT_NAME"
release_require_env_file
release_assert_image "mudaroba-backend:${TARGET_RELEASE}" "$TARGET_RELEASE"
release_assert_image "mudaroba-frontend:${TARGET_RELEASE}" "$TARGET_RELEASE"

release_log "entering a controlled maintenance window for code rollback"
release_compose_prod stop \
  nginx frontend backend celeryworker celery_ai celery_recsys celerybeat
release_log "rolling all application containers back without changing database schema"
release_compose_prod up -d --no-build --no-deps --wait --wait-timeout 180 \
  backend frontend celeryworker celery_ai celery_recsys celerybeat nginx
release_compose_prod ps
"${RELEASE_SCRIPT_DIR}/postdeploy-smoke.sh" --base-url "$BASE_URL"
release_log "code rollback completed"
release_log "if the failed release changed data incompatibly, restore the matched PostgreSQL/Qdrant backups before serving writes"
