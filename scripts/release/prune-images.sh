#!/usr/bin/env bash

set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

REGISTRY_NAMESPACE="${MUDAROBA_REGISTRY_NAMESPACE:-ghcr.io/mr-fulani}"
KEEP_RELEASES=()
APPLY=0

usage() {
  cat <<'EOF'
Usage: prune-images.sh \
  --keep FULL_GIT_SHA [--keep FULL_GIT_SHA ...] \
  [--registry host/namespace] \
  [--apply]

Dry-run is the default. Only SHA-tagged mudaroba-backend, mudaroba-frontend
and <registry>/pharmaturk-{backend,frontend} images are candidates. Images of
every --keep release and images used by any container (running or stopped)
are always kept. Removed images can be pulled again from the registry.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep) KEEP_RELEASES+=("${2:-}"); shift 2 ;;
    --registry) REGISTRY_NAMESPACE="${2:-}"; shift 2 ;;
    --apply) APPLY=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) release_die "unknown argument: $1" ;;
  esac
done

[[ "${#KEEP_RELEASES[@]}" -ge 1 ]] || release_die "at least one --keep release is required"
for release_id in "${KEEP_RELEASES[@]}"; do
  release_validate_sha "$release_id"
done
[[ "$REGISTRY_NAMESPACE" =~ ^[a-z0-9.-]+(:[0-9]+)?/[a-z0-9._/-]+$ ]] || \
  release_die "registry namespace must be a lowercase host/path"
release_require_command docker

is_kept() {
  local tag="$1"
  local release_id
  for release_id in "${KEEP_RELEASES[@]}"; do
    [[ "$tag" = "$release_id" ]] && return 0
  done
  return 1
}

used_image_ids=" "
container_ids="$(docker ps -a -q --no-trunc)"
if [[ -n "$container_ids" ]]; then
  # shellcheck disable=SC2086
  used_image_ids+="$(docker inspect --format '{{ .Image }}' $container_ids | tr '\n' ' ')"
fi

candidates=()
while read -r repository tag image_id; do
  case "$repository" in
    mudaroba-backend|mudaroba-frontend|"${REGISTRY_NAMESPACE}/pharmaturk-backend"|"${REGISTRY_NAMESPACE}/pharmaturk-frontend") ;;
    *) continue ;;
  esac
  [[ "$tag" =~ ^[0-9a-f]{40}$ ]] || continue
  if is_kept "$tag"; then
    release_log "keep: ${repository}:${tag}"
  elif [[ "$used_image_ids" = *" ${image_id} "* ]]; then
    release_log "keep (used by a container): ${repository}:${tag}"
  else
    candidates+=("${repository}:${tag}")
    release_log "candidate: ${repository}:${tag}"
  fi
done < <(docker image ls --no-trunc --format '{{ .Repository }} {{ .Tag }} {{ .ID }}')

release_log "candidates=${#candidates[@]} mode=$([[ "$APPLY" = "1" ]] && printf apply || printf dry-run)"
if [[ "$APPLY" != "1" || "${#candidates[@]}" -eq 0 ]]; then
  exit 0
fi

docker image rm "${candidates[@]}" >/dev/null
docker_root="$(docker info --format '{{ .DockerRootDir }}')"
release_log "removed ${#candidates[@]} image tags; free space on ${docker_root}: $(( $(release_free_kib "$docker_root") / 1024 / 1024 )) GiB"
