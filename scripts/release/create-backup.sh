#!/usr/bin/env bash

set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

PROJECT_NAME=""
PREVIOUS_RELEASE=""
BACKUP_ROOT=""
MINIMUM_FREE_GB=1

usage() {
  cat <<'EOF'
Usage: create-backup.sh \
  --project-name NAME \
  --previous-release FULL_GIT_SHA \
  --backup-root /absolute/private/path \
  [--minimum-free-gb N]

Creates and validates a PostgreSQL custom dump, an official Qdrant full-storage
snapshot containing every live collection, a protected environment copy, and a
release.manifest. The script never overwrites an existing backup and removes
only the temporary Qdrant snapshot it created.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-name) PROJECT_NAME="${2:-}"; shift 2 ;;
    --previous-release) PREVIOUS_RELEASE="${2:-}"; shift 2 ;;
    --backup-root) BACKUP_ROOT="${2:-}"; shift 2 ;;
    --minimum-free-gb) MINIMUM_FREE_GB="${2:-}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) release_die "unknown argument: $1" ;;
  esac
done

[[ "$PROJECT_NAME" =~ ^[a-z0-9][a-z0-9_-]+$ ]] || \
  release_die "explicit safe --project-name is required"
release_validate_sha "$PREVIOUS_RELEASE"
[[ "$BACKUP_ROOT" = /* && "$BACKUP_ROOT" != "/" ]] || \
  release_die "--backup-root must be an absolute non-root path"
[[ "$MINIMUM_FREE_GB" =~ ^[0-9]+$ ]] || \
  release_die "--minimum-free-gb must be a non-negative integer"

release_require_command docker
release_require_command tar
release_require_command find
release_require_env_file

mkdir -p "$BACKUP_ROOT"
[[ -d "$BACKUP_ROOT" && ! -L "$BACKUP_ROOT" && -w "$BACKUP_ROOT" ]] || \
  release_die "backup root must be a writable real directory"
BACKUP_ROOT="$(cd "$BACKUP_ROOT" && pwd -P)"

available_kb="$(df -Pk "$BACKUP_ROOT" | awk 'NR == 2 {print $4}')"
required_kb="$((MINIMUM_FREE_GB * 1024 * 1024))"
[[ "$available_kb" =~ ^[0-9]+$ && "$available_kb" -ge "$required_kb" ]] || \
  release_die "backup filesystem has less than ${MINIMUM_FREE_GB} GiB free"

export DEPLOY_PROJECT_NAME="$PROJECT_NAME"
postgres_container="$(release_compose_prod ps -q postgres)"
backend_container="$(release_compose_prod ps -q backend)"
qdrant_container="$(release_compose_prod ps -q qdrant)"
[[ -n "$postgres_container" && -n "$backend_container" && -n "$qdrant_container" ]] || \
  release_die "postgres, backend, and qdrant must already be running"

for container in "$postgres_container" "$backend_container" "$qdrant_container"; do
  [[ "$(docker inspect -f '{{.State.Running}}' "$container")" = "true" ]] || \
    release_die "required container is not running: $container"
done

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="${BACKUP_ROOT}/${stamp}_pre_${PREVIOUS_RELEASE:0:7}"
marker_file="${backup_dir}/.mudaroba-backup-in-progress"
[[ ! -e "$backup_dir" ]] || release_die "backup directory already exists"
mkdir -m 700 "$backup_dir"
: > "$marker_file"
chmod 600 "$marker_file"

backup_completed=0
qdrant_snapshot_name=""

cleanup_qdrant_snapshot() {
  if [[ -n "$qdrant_snapshot_name" ]]; then
    docker exec "$backend_container" poetry run python -c '
import sys
import urllib.parse
import urllib.request

snapshot = urllib.parse.quote(sys.argv[1], safe="")
request = urllib.request.Request(
    f"http://qdrant:6333/snapshots/{snapshot}",
    method="DELETE",
)
urllib.request.urlopen(request, timeout=60).read()
' "$qdrant_snapshot_name" >/dev/null 2>&1 || true
  fi
}

cleanup_on_exit() {
  cleanup_qdrant_snapshot
  if [[ "$backup_completed" != "1" && -f "$marker_file" ]]; then
    find "$backup_dir" -xdev -depth -delete >/dev/null 2>&1 || true
  fi
}
trap cleanup_on_exit EXIT

release_log "creating PostgreSQL custom dump"
docker exec "$postgres_container" sh -ec \
  'exec pg_dump --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --format=custom' \
  > "${backup_dir}/postgres.dump"
chmod 600 "${backup_dir}/postgres.dump"

release_log "creating official Qdrant full-storage snapshot"
qdrant_snapshot_name="$(
  docker exec "$backend_container" poetry run python -c '
import json
import urllib.request

request = urllib.request.Request(
    "http://qdrant:6333/snapshots",
    data=b"{}",
    headers={"Content-Type": "application/json"},
    method="POST",
)
print(json.load(urllib.request.urlopen(request, timeout=300))["result"]["name"])
'
)"
[[ "$qdrant_snapshot_name" =~ ^[A-Za-z0-9._-]+$ ]] || \
  release_die "Qdrant returned an unsafe full-snapshot name"
snapshot_path="$(
  docker exec "$qdrant_container" find /qdrant/snapshots \
    -type f -name "$qdrant_snapshot_name" -print -quit
)"
[[ -n "$snapshot_path" ]] || release_die "Qdrant full snapshot file not found"
docker cp \
  "${qdrant_container}:${snapshot_path}" \
  "${backup_dir}/qdrant.snapshot" >/dev/null
chmod 600 "${backup_dir}/qdrant.snapshot"
install -m 600 "${RELEASE_REPO_ROOT}/.env" "${backup_dir}/env.backup"

PG_RESTORE_CONTAINER="$postgres_container" \
  "${RELEASE_SCRIPT_DIR}/prepare-backup-manifest.sh" \
  --postgres-dump "${backup_dir}/postgres.dump" \
  --qdrant-snapshot "${backup_dir}/qdrant.snapshot" \
  --previous-release "$PREVIOUS_RELEASE" \
  --output "${backup_dir}/release.manifest"
chmod 600 "${backup_dir}/release.manifest"

docker exec -i "$postgres_container" pg_restore --list \
  < "${backup_dir}/postgres.dump" >/dev/null
tar -tf "${backup_dir}/qdrant.snapshot" >/dev/null
release_verify_backup_manifest "${backup_dir}/release.manifest" "$PREVIOUS_RELEASE"

cleanup_qdrant_snapshot
qdrant_snapshot_name=""
rm "$marker_file"
backup_completed=1
trap - EXIT

release_log "backup ready: ${backup_dir}"
printf '%s\n' "$backup_dir"
