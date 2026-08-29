#!/usr/bin/env bash

set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

BACKUP_ROOT=""
KEEP=7
APPLY=0
CONFIRMATION=""
PROTECTED_PATHS=()

usage() {
  cat <<'EOF'
Usage: prune-backups.sh \
  --backup-root /absolute/private/path \
  [--keep N] \
  [--protect /absolute/backup/path ...] \
  [--apply --confirm "PRUNE BACKUPS /absolute/private/path"]

Dry-run is the default. Only direct child directories with PostgreSQL/Qdrant
artifacts, a protected environment copy, and a mudaroba-release-backup-v1
manifest are candidates. Both the current file names and the historical
``manifest.env``/``env.production`` layouts are recognised. The newest N valid
backups and every explicitly protected path are always kept.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup-root) BACKUP_ROOT="${2:-}"; shift 2 ;;
    --keep) KEEP="${2:-}"; shift 2 ;;
    --protect) PROTECTED_PATHS+=("${2:-}"); shift 2 ;;
    --apply) APPLY=1; shift ;;
    --confirm) CONFIRMATION="${2:-}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) release_die "unknown argument: $1" ;;
  esac
done

[[ "$BACKUP_ROOT" = /* && "$BACKUP_ROOT" != "/" ]] || \
  release_die "--backup-root must be an absolute non-root path"
[[ "$KEEP" =~ ^[0-9]+$ && "$KEEP" -ge 2 ]] || \
  release_die "--keep must be an integer of at least 2"
[[ -d "$BACKUP_ROOT" && ! -L "$BACKUP_ROOT" ]] || \
  release_die "backup root must be a real directory"
BACKUP_ROOT="$(cd "$BACKUP_ROOT" && pwd -P)"

if [[ "$APPLY" = "1" ]]; then
  [[ "$CONFIRMATION" = "PRUNE BACKUPS ${BACKUP_ROOT}" ]] || \
    release_die "confirmation must exactly match: PRUNE BACKUPS ${BACKUP_ROOT}"
elif [[ -n "$CONFIRMATION" ]]; then
  release_die "--confirm is accepted only together with --apply"
fi

protected_paths=()
for raw_path in "${PROTECTED_PATHS[@]}"; do
  [[ "$raw_path" = /* && -d "$raw_path" && ! -L "$raw_path" ]] || \
    release_die "protected backup must be an existing absolute directory"
  path="$(cd "$raw_path" && pwd -P)"
  [[ "$(dirname "$path")" = "$BACKUP_ROOT" ]] || \
    release_die "protected backup must be a direct child of backup root"
  protected_paths+=("$path")
done

is_protected() {
  local candidate="$1"
  local protected_path
  for protected_path in "${protected_paths[@]}"; do
    [[ "$candidate" = "$protected_path" ]] && return 0
  done
  return 1
}

valid_backups=()
while IFS= read -r path; do
  name="$(basename "$path")"
  manifest=""
  if [[ ! "$name" =~ ^[0-9]{8}T[0-9]{6}Z_ ]]; then
    release_log "skipping unrecognised directory: $path"
    continue
  fi
  if [[ -s "$path/release.manifest" && ! -L "$path/release.manifest" ]]; then
    manifest="$path/release.manifest"
  elif [[ -s "$path/manifest.env" && ! -L "$path/manifest.env" ]]; then
    manifest="$path/manifest.env"
  fi
  environment_copy="$(
    find "$path" -mindepth 1 -maxdepth 1 -type f \
      \( -name 'env.backup' -o -name 'env.production' -o -name 'env.before-*' \) \
      -size +0c -print -quit
  )"
  if [[ -z "$manifest" || ! -s "$path/postgres.dump" || \
        -L "$path/postgres.dump" || ! -s "$path/qdrant.snapshot" || \
        -L "$path/qdrant.snapshot" || -z "$environment_copy" ]]; then
    release_log "skipping incomplete backup: $path"
    continue
  fi
  if ! grep -qx 'format=mudaroba-release-backup-v1' "$manifest"; then
    release_log "skipping backup with unknown manifest: $path"
    continue
  fi
  valid_backups+=("$path")
done < <(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -print | sort -r)

delete_candidates=()
for index in "${!valid_backups[@]}"; do
  path="${valid_backups[$index]}"
  if [[ "$index" -lt "$KEEP" ]] || is_protected "$path"; then
    release_log "keep: $path"
  else
    delete_candidates+=("$path")
    release_log "candidate: $path"
  fi
done

release_log "valid=${#valid_backups[@]} keep_newest=${KEEP} candidates=${#delete_candidates[@]} mode=$([[ "$APPLY" = "1" ]] && printf apply || printf dry-run)"

if [[ "$APPLY" != "1" ]]; then
  exit 0
fi

for path in "${delete_candidates[@]}"; do
  [[ "$(dirname "$path")" = "$BACKUP_ROOT" && -d "$path" && ! -L "$path" ]] || \
    release_die "candidate changed during pruning: $path"
  release_log "deleting expired backup: $path"
  find "$path" -xdev -depth -delete
done
