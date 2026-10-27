#!/usr/bin/env bash

set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

PROJECT_NAME=""
RELEASE_ID=""
PREVIOUS_RELEASE=""
PREVIOUS_FRONTEND_RELEASE=""
BACKUP_ROOT=""
APPLY=0

usage() {
  cat <<'EOF'
Usage: prepare-disk.sh \
  --project-name NAME \
  --release-id FULL_GIT_SHA \
  --previous-release FULL_GIT_SHA \
  [--previous-frontend-release FULL_GIT_SHA] \
  --backup-root /absolute/private/path \
  [--apply]

Run before 'git merge' and create-backup.sh. Dry-run is the default. With
--apply it removes stopped helper containers (<project>-once-*,
<project>-aibatch-*, Compose one-offs <project>-<service>-run-*), release images
of every SHA except the new and previous ones (prune-images.sh) and pre-deploy
backups except the newest two (prune-backups.sh), then fails unless the disk
has room for a new backup plus the images pull-images.sh requires. Running
containers, application service containers and images used by any container
are never removed.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-name) PROJECT_NAME="${2:-}"; shift 2 ;;
    --release-id) RELEASE_ID="${2:-}"; shift 2 ;;
    --previous-release) PREVIOUS_RELEASE="${2:-}"; shift 2 ;;
    --previous-frontend-release) PREVIOUS_FRONTEND_RELEASE="${2:-}"; shift 2 ;;
    --backup-root) BACKUP_ROOT="${2:-}"; shift 2 ;;
    --apply) APPLY=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) release_die "unknown argument: $1" ;;
  esac
done

[[ "$PROJECT_NAME" =~ ^[a-z0-9][a-z0-9_-]+$ ]] || \
  release_die "explicit safe --project-name is required"
release_validate_sha "$RELEASE_ID"
release_validate_sha "$PREVIOUS_RELEASE"
PREVIOUS_FRONTEND_RELEASE="${PREVIOUS_FRONTEND_RELEASE:-$PREVIOUS_RELEASE}"
release_validate_sha "$PREVIOUS_FRONTEND_RELEASE"
[[ "$BACKUP_ROOT" = /* && "$BACKUP_ROOT" != "/" && -d "$BACKUP_ROOT" && ! -L "$BACKUP_ROOT" ]] || \
  release_die "--backup-root must be an existing absolute real directory"
BACKUP_ROOT="$(cd "$BACKUP_ROOT" && pwd -P)"
release_require_command docker

docker_root="$(docker info --format '{{ .DockerRootDir }}')" || \
  release_die "cannot determine Docker data root"

helpers=()
while read -r name; do
  if [[ "$name" =~ ^${PROJECT_NAME}-(once|aibatch)- || \
        "$name" =~ ^${PROJECT_NAME}-[a-z0-9_]+-run-[0-9a-f]+$ ]]; then
    helpers+=("$name")
    release_log "stopped helper container: $name"
  fi
done < <(docker ps -a --filter status=exited --filter status=dead --format '{{ .Names }}')
if [[ "$APPLY" = "1" && "${#helpers[@]}" -gt 0 ]]; then
  docker rm "${helpers[@]}" >/dev/null
  release_log "removed ${#helpers[@]} stopped helper containers"
fi

apply_flag=()
[[ "$APPLY" = "1" ]] && apply_flag=(--apply)
"${RELEASE_SCRIPT_DIR}/prune-images.sh" "${apply_flag[@]}" \
  --keep "$RELEASE_ID" --keep "$PREVIOUS_RELEASE" --keep "$PREVIOUS_FRONTEND_RELEASE"

if [[ "$APPLY" = "1" ]]; then
  "${RELEASE_SCRIPT_DIR}/prune-backups.sh" \
    --backup-root "$BACKUP_ROOT" \
    --keep "$RELEASE_BACKUP_KEEP" \
    --apply \
    --confirm "PRUNE BACKUPS ${BACKUP_ROOT}"
  release_require_release_space "$BACKUP_ROOT" "$docker_root"
else
  "${RELEASE_SCRIPT_DIR}/prune-backups.sh" \
    --backup-root "$BACKUP_ROOT" \
    --keep "$RELEASE_BACKUP_KEEP"
  release_log "dry-run: free space is checked after cleanup with --apply"
fi
