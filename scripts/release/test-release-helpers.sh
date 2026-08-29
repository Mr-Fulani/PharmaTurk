#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
temp_root="$(mktemp -d)"
cleanup() {
  find "$temp_root" -xdev -depth -delete >/dev/null 2>&1 || true
}
trap cleanup EXIT

"${SCRIPT_DIR}/create-backup.sh" --help >/dev/null
"${SCRIPT_DIR}/prune-backups.sh" --help >/dev/null

backup_root="${temp_root}/backups"
mkdir -p "$backup_root"
backup_root="$(cd "$backup_root" && pwd -P)"
for index in 01 02 03 04; do
  path="${backup_root}/202608${index}T120000Z_pre_example"
  mkdir -m 700 "$path"
  printf 'format=mudaroba-release-backup-v1\n' > "$path/release.manifest"
  printf 'postgres\n' > "$path/postgres.dump"
  printf 'qdrant\n' > "$path/qdrant.snapshot"
  printf 'env\n' > "$path/env.backup"
done

# Historical backups used these two names. They remain valid retention
# candidates; otherwise the safety filter would never reclaim old production
# backups and a nearly full disk would keep growing.
mv "${backup_root}/20260801T120000Z_pre_example/release.manifest" \
  "${backup_root}/20260801T120000Z_pre_example/manifest.env"
mv "${backup_root}/20260801T120000Z_pre_example/env.backup" \
  "${backup_root}/20260801T120000Z_pre_example/env.production"

protected="${backup_root}/20260801T120000Z_pre_example"
dry_run="$(
  "${SCRIPT_DIR}/prune-backups.sh" \
    --backup-root "$backup_root" \
    --keep 2 \
    --protect "$protected"
)"
grep -F "candidate: ${backup_root}/20260802T120000Z_pre_example" <<< "$dry_run" >/dev/null
[[ -d "${backup_root}/20260802T120000Z_pre_example" ]]

"${SCRIPT_DIR}/prune-backups.sh" \
  --backup-root "$backup_root" \
  --keep 2 \
  --protect "$protected" \
  --apply \
  --confirm "PRUNE BACKUPS ${backup_root}" >/dev/null

[[ -d "$protected" ]]
[[ ! -e "${backup_root}/20260802T120000Z_pre_example" ]]
[[ -d "${backup_root}/20260803T120000Z_pre_example" ]]
[[ -d "${backup_root}/20260804T120000Z_pre_example" ]]

printf '%s\n' "release helper tests passed"
