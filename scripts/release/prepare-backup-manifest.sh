#!/usr/bin/env bash

set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

POSTGRES_DUMP=""
QDRANT_SNAPSHOT=""
PREVIOUS_RELEASE=""
OUTPUT_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --postgres-dump) POSTGRES_DUMP="${2:-}"; shift 2 ;;
    --qdrant-snapshot) QDRANT_SNAPSHOT="${2:-}"; shift 2 ;;
    --previous-release) PREVIOUS_RELEASE="${2:-}"; shift 2 ;;
    --output) OUTPUT_FILE="${2:-}"; shift 2 ;;
    *) release_die "unknown argument: $1" ;;
  esac
done

release_validate_sha "$PREVIOUS_RELEASE"
[[ -f "$POSTGRES_DUMP" && -s "$POSTGRES_DUMP" ]] || release_die "PostgreSQL dump is missing or empty"
[[ -f "$QDRANT_SNAPSHOT" && -s "$QDRANT_SNAPSHOT" ]] || release_die "Qdrant snapshot is missing or empty"
[[ -n "$OUTPUT_FILE" ]] || release_die "--output is required"
[[ ! -e "$OUTPUT_FILE" ]] || release_die "output already exists; refusing to overwrite it"

if command -v pg_restore >/dev/null 2>&1; then
  pg_restore --list "$POSTGRES_DUMP" >/dev/null || release_die "PostgreSQL dump is not readable by pg_restore"
else
  release_die "pg_restore is required to validate the PostgreSQL dump"
fi

output_dir="$(cd "$(dirname "$OUTPUT_FILE")" && pwd)"
output_name="$(basename "$OUTPUT_FILE")"
temp_file="$(mktemp "${output_dir}/.${output_name}.XXXXXX")"
trap 'rm -f "$temp_file"' EXIT

{
  printf 'format=mudaroba-release-backup-v1\n'
  printf 'created_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'previous_release=%s\n' "$PREVIOUS_RELEASE"
  printf 'postgres_dump=%s\n' "$(cd "$(dirname "$POSTGRES_DUMP")" && pwd)/$(basename "$POSTGRES_DUMP")"
  printf 'postgres_sha256=%s\n' "$(release_sha256 "$POSTGRES_DUMP")"
  printf 'qdrant_snapshot=%s\n' "$(cd "$(dirname "$QDRANT_SNAPSHOT")" && pwd)/$(basename "$QDRANT_SNAPSHOT")"
  printf 'qdrant_sha256=%s\n' "$(release_sha256 "$QDRANT_SNAPSHOT")"
} > "$temp_file"
chmod 600 "$temp_file"
mv "$temp_file" "${output_dir}/${output_name}"
trap - EXIT
release_log "validated backup manifest created at ${output_dir}/${output_name}"
