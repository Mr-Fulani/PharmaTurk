#!/usr/bin/env bash

set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

ENVIRONMENT=""
RELEASE_ID=""
PREVIOUS_RELEASE=""
FRONTEND_RELEASE=""
PREVIOUS_FRONTEND_RELEASE=""
BACKUP_MANIFEST=""
BASE_URL=""
CONFIRMATION=""
PROJECT_NAME=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --environment) ENVIRONMENT="${2:-}"; shift 2 ;;
    --release-id) RELEASE_ID="${2:-}"; shift 2 ;;
    --previous-release) PREVIOUS_RELEASE="${2:-}"; shift 2 ;;
    --frontend-release) FRONTEND_RELEASE="${2:-}"; shift 2 ;;
    --previous-frontend-release) PREVIOUS_FRONTEND_RELEASE="${2:-}"; shift 2 ;;
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
FRONTEND_RELEASE="${FRONTEND_RELEASE:-$RELEASE_ID}"
PREVIOUS_FRONTEND_RELEASE="${PREVIOUS_FRONTEND_RELEASE:-$PREVIOUS_RELEASE}"
release_validate_sha "$FRONTEND_RELEASE"
release_validate_sha "$PREVIOUS_FRONTEND_RELEASE"
[[ "$RELEASE_ID" != "$PREVIOUS_RELEASE" ]] || \
  release_die "release id and previous release must be different"
release_require_clean_sha "$RELEASE_ID"
release_require_env_file
release_verify_backup_manifest "$BACKUP_MANIFEST" "$PREVIOUS_RELEASE"
[[ "$BASE_URL" =~ ^https://[^/]+$ ]] || release_die "invalid HTTPS base URL"
[[ "$PROJECT_NAME" =~ ^[a-z0-9][a-z0-9_-]+$ ]] || release_die "explicit safe --project-name is required"
[[ "$CONFIRMATION" = "DEPLOY ${ENVIRONMENT} ${RELEASE_ID}" ]] || \
  release_die "confirmation must exactly match: DEPLOY ${ENVIRONMENT} ${RELEASE_ID}"

export IMAGE_TAG="$FRONTEND_RELEASE"
export BACKEND_IMAGE_TAG="$RELEASE_ID"
export RUN_MIGRATIONS=0
export DEPLOY_PROJECT_NAME="$PROJECT_NAME"

release_assert_image "mudaroba-backend:${RELEASE_ID}" "$RELEASE_ID"
release_assert_image "mudaroba-frontend:${FRONTEND_RELEASE}" "$FRONTEND_RELEASE"
release_assert_image "mudaroba-backend:${PREVIOUS_RELEASE}" "$PREVIOUS_RELEASE"
release_assert_image "mudaroba-frontend:${PREVIOUS_FRONTEND_RELEASE}" "$PREVIOUS_FRONTEND_RELEASE"

release_log "printing migration plan"
release_compose_prod --profile ops run --rm --no-deps migrate migrate --plan
release_log "entering a controlled maintenance window before schema changes"
release_compose_prod stop \
  nginx frontend backend celeryworker celery_ai celery_recsys celerybeat
release_log "ensuring existing state services are running without recreating containers or volumes"
release_compose_prod up -d --no-recreate postgres redis redis-cache qdrant
release_log "applying committed migrations exactly once"
# Сайт уже остановлен: если миграция упадёт, поднимаем прошлый релиз, иначе прод
# остаётся лежать (27.10.2026: ~4 минуты простоя). Миграции в проекте только добавляют,
# прошлый код работает поверх частично применённой схемы.
restart_previous_release() {
  release_log "ERROR: migrations failed; restarting the previous release ${PREVIOUS_RELEASE}"
  export IMAGE_TAG="$PREVIOUS_FRONTEND_RELEASE" BACKEND_IMAGE_TAG="$PREVIOUS_RELEASE"
  release_compose_prod up -d --no-build --no-deps --wait --wait-timeout 180 \
    backend frontend celeryworker celery_ai celery_recsys celerybeat nginx || \
    release_log "ERROR: the previous release did not start; start it manually"
}
trap restart_previous_release ERR
release_compose_prod --profile ops run --rm --no-deps migrate migrate --noinput
trap - ERR
release_log "starting one consistent release without rebuilding or automatic migrations"
release_compose_prod up -d --no-build --no-deps --wait --wait-timeout 180 \
  backend frontend celeryworker celery_ai celery_recsys celerybeat nginx
release_compose_prod ps

"${RELEASE_SCRIPT_DIR}/postdeploy-smoke.sh" --base-url "$BASE_URL"
python3 "${RELEASE_SCRIPT_DIR}/pin_versions.py" --env "${RELEASE_REPO_ROOT}/.env" \
  --backend "$RELEASE_ID" --frontend "$FRONTEND_RELEASE"
release_log "deploy completed: ${ENVIRONMENT}:${RELEASE_ID}"
release_log "removing release images older than the previous release"
"${RELEASE_SCRIPT_DIR}/prune-images.sh" --apply \
  --keep "$RELEASE_ID" --keep "$FRONTEND_RELEASE" \
  --keep "$PREVIOUS_RELEASE" --keep "$PREVIOUS_FRONTEND_RELEASE" || \
  release_log "WARNING: image pruning failed; the deploy itself succeeded, review with prune-images.sh"
release_log "removing pre-deploy backups except the newest ${RELEASE_BACKUP_KEEP} and the current one"
release_prune_backups_after_deploy "$BACKUP_MANIFEST" || \
  release_log "WARNING: backup pruning failed; the deploy itself succeeded, review with prune-backups.sh"
release_log "keep previous images and the current backup until the observation window closes"
