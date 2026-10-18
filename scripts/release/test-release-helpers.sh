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
"${SCRIPT_DIR}/prune-images.sh" --help >/dev/null

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

# Image pruning and the free-space gate run against stub docker/df commands.
stub_bin="${temp_root}/bin"
mkdir -p "$stub_bin"
export FAKE_DOCKER_LOG="${temp_root}/docker.log"
export FAKE_IMAGES="${temp_root}/images.txt"
export FAKE_DF_AVAIL_KIB=0
: > "$FAKE_DOCKER_LOG"
cat > "${stub_bin}/docker" <<'EOF'
#!/usr/bin/env bash
case "$1 ${2:-}" in
  "info "*) printf '/var/lib/docker\n' ;;
  "ps "*) printf 'container1\n' ;;
  "inspect "*) printf 'sha256:used\n' ;;
  "image ls") cat "$FAKE_IMAGES" ;;
  "image rm") shift 2; printf 'image rm %s\n' "$*" >> "$FAKE_DOCKER_LOG" ;;
  "pull "*) printf 'pull %s\n' "$2" >> "$FAKE_DOCKER_LOG" ;;
  *) printf 'unexpected docker call: %s\n' "$*" >&2; exit 1 ;;
esac
EOF
cat > "${stub_bin}/df" <<'EOF'
#!/usr/bin/env bash
printf 'Filesystem 1024-blocks Used Available Capacity Mounted\n'
printf '/dev/sda1 39000000 1000 %s 99%% /\n' "$FAKE_DF_AVAIL_KIB"
EOF
chmod +x "${stub_bin}/docker" "${stub_bin}/df"

sha_current="$(printf '%040d' 0 | tr 0 a)"
sha_previous="$(printf '%040d' 0 | tr 0 b)"
sha_old="$(printf '%040d' 0 | tr 0 c)"
sha_in_use="$(printf '%040d' 0 | tr 0 d)"

FAKE_DF_AVAIL_KIB=$(( 3 * 1024 * 1024 ))
if pull_output="$(PATH="${stub_bin}:${PATH}" "${SCRIPT_DIR}/pull-images.sh" --release-id "$sha_current" 2>&1)"; then
  printf 'pull-images.sh must refuse to pull with less than 4 GiB free\n' >&2
  exit 1
fi
grep -F "at least 4 GiB required" <<< "$pull_output" >/dev/null
[[ ! -s "$FAKE_DOCKER_LOG" ]]

cat > "$FAKE_IMAGES" <<EOF
mudaroba-backend ${sha_current} sha256:current
ghcr.io/mr-fulani/pharmaturk-backend ${sha_current} sha256:current
mudaroba-backend ${sha_previous} sha256:previous
mudaroba-backend ${sha_old} sha256:old
ghcr.io/mr-fulani/pharmaturk-backend ${sha_old} sha256:old
mudaroba-frontend ${sha_in_use} sha256:used
ghcr.io/other/pharmaturk-backend ${sha_old} sha256:other
mudaroba-backend local sha256:local
redis 7-alpine sha256:redis
EOF

prune_output="$(PATH="${stub_bin}:${PATH}" "${SCRIPT_DIR}/prune-images.sh" \
  --keep "$sha_current" --keep "$sha_previous")"
grep -F "candidates=2 mode=dry-run" <<< "$prune_output" >/dev/null
grep -F "keep (used by a container): mudaroba-frontend:${sha_in_use}" <<< "$prune_output" >/dev/null
[[ ! -s "$FAKE_DOCKER_LOG" ]]

FAKE_DF_AVAIL_KIB=$(( 9 * 1024 * 1024 ))
PATH="${stub_bin}:${PATH}" "${SCRIPT_DIR}/prune-images.sh" \
  --keep "$sha_current" --keep "$sha_previous" --apply >/dev/null
[[ "$(cat "$FAKE_DOCKER_LOG")" = "image rm mudaroba-backend:${sha_old} ghcr.io/mr-fulani/pharmaturk-backend:${sha_old}" ]]

printf '%s\n' "release helper tests passed"
