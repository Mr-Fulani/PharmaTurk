#!/usr/bin/env bash

set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

RELEASE_ID=""
REGISTRY_NAMESPACE="${MUDAROBA_REGISTRY_NAMESPACE:-ghcr.io/mr-fulani}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --release-id) RELEASE_ID="${2:-}"; shift 2 ;;
    --registry) REGISTRY_NAMESPACE="${2:-}"; shift 2 ;;
    *) release_die "unknown argument: $1" ;;
  esac
done

release_validate_sha "$RELEASE_ID"
release_require_command docker
[[ "$REGISTRY_NAMESPACE" =~ ^[a-z0-9.-]+(:[0-9]+)?/[a-z0-9._/-]+$ ]] || \
  release_die "registry namespace must be a lowercase host/path"

backend_source="${REGISTRY_NAMESPACE}/pharmaturk-backend:${RELEASE_ID}"
frontend_source="${REGISTRY_NAMESPACE}/pharmaturk-frontend:${RELEASE_ID}"
backend_target="mudaroba-backend:${RELEASE_ID}"
frontend_target="mudaroba-frontend:${RELEASE_ID}"

release_log "pulling immutable release images"
docker pull "$backend_source"
docker pull "$frontend_source"

assert_runtime_user() {
  local image_name="$1"
  local expected_user="$2"
  local actual_user
  actual_user="$(docker image inspect "$image_name" --format '{{ .Config.User }}')" || \
    release_die "cannot inspect image runtime user: $image_name"
  [[ "$actual_user" = "$expected_user" ]] || \
    release_die "unexpected runtime user for $image_name: $actual_user"
}

release_assert_image "$backend_source" "$RELEASE_ID"
release_assert_image "$frontend_source" "$RELEASE_ID"
assert_runtime_user "$backend_source" "app"
assert_runtime_user "$frontend_source" "node"

docker tag "$backend_source" "$backend_target"
docker tag "$frontend_source" "$frontend_target"

release_assert_image "$backend_target" "$RELEASE_ID"
release_assert_image "$frontend_target" "$RELEASE_ID"
assert_runtime_user "$backend_target" "app"
assert_runtime_user "$frontend_target" "node"
release_log "release images ready: ${RELEASE_ID}"
