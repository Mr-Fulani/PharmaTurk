#!/usr/bin/env bash

set -Eeuo pipefail

RELEASE_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RELEASE_REPO_ROOT="$(cd "${RELEASE_SCRIPT_DIR}/../.." && pwd)"
RELEASE_COMPOSE_BASE="${RELEASE_REPO_ROOT}/docker-compose.yml"
RELEASE_COMPOSE_PROD="${RELEASE_REPO_ROOT}/docker-compose.prod.yml"
RELEASE_COMPOSE_SMOKE="${RELEASE_REPO_ROOT}/docker-compose.smoke.yml"

release_log() {
  printf '[release] %s\n' "$*"
}

release_die() {
  printf '[release] ERROR: %s\n' "$*" >&2
  exit 1
}

release_require_command() {
  command -v "$1" >/dev/null 2>&1 || release_die "required command not found: $1"
}

release_validate_environment() {
  case "$1" in
    local|staging|production) ;;
    *) release_die "environment must be local, staging, or production" ;;
  esac
}

release_validate_tag() {
  [[ "$1" =~ ^[a-z0-9][a-z0-9._-]{6,63}$ ]] || \
    release_die "release id must be 7-64 lowercase tag-safe characters"
}

release_validate_sha() {
  [[ "$1" =~ ^[0-9a-f]{40}$ ]] || \
    release_die "staging/production release id must be the full 40-character Git SHA"
}

release_require_clean_sha() {
  local release_id="$1"
  local head_sha
  release_validate_sha "$release_id"
  head_sha="$(git -C "$RELEASE_REPO_ROOT" rev-parse HEAD)"
  [[ "$release_id" = "$head_sha" ]] || \
    release_die "release id does not match the checked-out Git HEAD"
  [[ -z "$(git -C "$RELEASE_REPO_ROOT" status --porcelain)" ]] || \
    release_die "working tree is dirty; commit and review the exact release first"
}

release_require_env_file() {
  [[ -f "${RELEASE_REPO_ROOT}/.env" ]] || release_die ".env is missing"
  git -C "$RELEASE_REPO_ROOT" check-ignore -q .env || \
    release_die ".env is not ignored by Git"
}

release_compose_prod() {
  docker compose \
    --project-name "$DEPLOY_PROJECT_NAME" \
    -f "$RELEASE_COMPOSE_BASE" \
    -f "$RELEASE_COMPOSE_PROD" \
    "$@"
}

release_assert_image() {
  local image_name="$1"
  local release_id="$2"
  local revision
  revision="$(docker image inspect "$image_name" \
    --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' 2>/dev/null)" || \
    release_die "required image is missing: $image_name"
  [[ "$revision" = "$release_id" ]] || \
    release_die "image revision mismatch for $image_name"
}

release_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

release_manifest_value() {
  local key="$1"
  local manifest="$2"
  local count
  count="$(grep -c "^${key}=" "$manifest" || true)"
  [[ "$count" = "1" ]] || release_die "backup manifest must contain exactly one ${key} entry"
  awk -v prefix="${key}=" 'index($0, prefix) == 1 { print substr($0, length(prefix) + 1) }' "$manifest"
}

release_verify_backup_manifest() {
  local manifest="$1"
  local expected_previous_release="$2"
  local postgres_dump qdrant_snapshot postgres_expected qdrant_expected

  [[ -f "$manifest" && -s "$manifest" ]] || release_die "validated backup manifest is required"
  grep -qx 'format=mudaroba-release-backup-v1' "$manifest" || release_die "unknown backup manifest format"
  [[ "$(release_manifest_value previous_release "$manifest")" = "$expected_previous_release" ]] || \
    release_die "backup manifest release mismatch"

  postgres_dump="$(release_manifest_value postgres_dump "$manifest")"
  qdrant_snapshot="$(release_manifest_value qdrant_snapshot "$manifest")"
  postgres_expected="$(release_manifest_value postgres_sha256 "$manifest")"
  qdrant_expected="$(release_manifest_value qdrant_sha256 "$manifest")"
  [[ -f "$postgres_dump" && -s "$postgres_dump" ]] || release_die "manifest PostgreSQL dump is unavailable"
  [[ -f "$qdrant_snapshot" && -s "$qdrant_snapshot" ]] || release_die "manifest Qdrant snapshot is unavailable"
  [[ "$(release_sha256 "$postgres_dump")" = "$postgres_expected" ]] || release_die "PostgreSQL dump checksum mismatch"
  [[ "$(release_sha256 "$qdrant_snapshot")" = "$qdrant_expected" ]] || release_die "Qdrant snapshot checksum mismatch"
}
