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
"${SCRIPT_DIR}/prepare-disk.sh" --help >/dev/null

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

# deploy.sh after a successful release: the newest two valid backups and the
# current one (from the manifest) stay, older valid ones are removed.
(
  source "${SCRIPT_DIR}/common.sh"
  deploy_root="${temp_root}/deploy-backups"
  mkdir -p "$deploy_root"
  for index in 01 02 03 04 05 06; do
    path="${deploy_root}/202609${index}T120000Z_pre_example"
    mkdir -m 700 "$path"
    printf 'format=mudaroba-release-backup-v1\n' > "$path/release.manifest"
    printf 'postgres\n' > "$path/postgres.dump"
    printf 'qdrant\n' > "$path/qdrant.snapshot"
    printf 'env\n' > "$path/env.backup"
  done
  mkdir "${deploy_root}/backend-release-abc"  # not a release backup: never touched
  # The deploy's own backup is protected even when it is not among the newest.
  current="${deploy_root}/20260901T120000Z_pre_example"
  release_prune_backups_after_deploy "${current}/release.manifest" >/dev/null
  [[ -d "$current" ]]
  [[ ! -e "${deploy_root}/20260902T120000Z_pre_example" ]]
  [[ ! -e "${deploy_root}/20260903T120000Z_pre_example" ]]
  [[ ! -e "${deploy_root}/20260904T120000Z_pre_example" ]]
  for index in 05 06; do [[ -d "${deploy_root}/202609${index}T120000Z_pre_example" ]]; done
  [[ -d "${deploy_root}/backend-release-abc" ]]
)
grep -F 'release_prune_backups_after_deploy "$BACKUP_MANIFEST"' "${SCRIPT_DIR}/deploy.sh" >/dev/null

# Image pruning and the free-space gate run against stub docker/df commands.
stub_bin="${temp_root}/bin"
mkdir -p "$stub_bin"
export FAKE_DOCKER_LOG="${temp_root}/docker.log"
export FAKE_IMAGES="${temp_root}/images.txt"
export FAKE_STOPPED="${temp_root}/stopped.txt"
export FAKE_DF_AVAIL_KIB=0
: > "$FAKE_STOPPED"
: > "$FAKE_DOCKER_LOG"
cat > "${stub_bin}/docker" <<'EOF'
#!/usr/bin/env bash
case "$1 ${2:-}" in
  "info "*) printf '/var/lib/docker\n' ;;
  "ps "*)
    if [[ " $* " = *" --filter "* ]]; then cat "$FAKE_STOPPED"; else printf 'container1\n'; fi ;;
  "rm "*) shift; printf 'rm %s\n' "$*" >> "$FAKE_DOCKER_LOG" ;;
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

# Free space for the whole release is checked before the backup: the newest
# backup's size plus the 4 GiB pull-images.sh needs.
space_root="${temp_root}/space-backups"
mkdir -p "${space_root}/20261001T120000Z_pre_example"
printf 'format=mudaroba-release-backup-v1\n' > "${space_root}/20261001T120000Z_pre_example/release.manifest"
head -c $(( 2 * 1024 * 1024 )) /dev/zero > "${space_root}/20261001T120000Z_pre_example/postgres.dump"
FAKE_DF_AVAIL_KIB=$(( 4 * 1024 * 1024 + 1024 ))
if space_output="$(PATH="${stub_bin}:${PATH}" bash -c \
    'source "$1/common.sh"; release_require_release_space "$2" /var/lib/docker' \
    _ "$SCRIPT_DIR" "$space_root" 2>&1)"; then
  printf 'the release space check must count the backup on top of 4 GiB\n' >&2
  exit 1
fi
grep -F "the release needs 4.0 GiB" <<< "$space_output" >/dev/null
FAKE_DF_AVAIL_KIB=$(( 5 * 1024 * 1024 ))
PATH="${stub_bin}:${PATH}" bash -c \
  'source "$1/common.sh"; release_require_release_space "$2" /var/lib/docker' \
  _ "$SCRIPT_DIR" "$space_root" >/dev/null
grep -F 'release_require_release_space "$BACKUP_ROOT" "$docker_root"' "${SCRIPT_DIR}/create-backup.sh" >/dev/null

# prepare-disk.sh before git merge: stopped helpers, old images and backups
# beyond the newest two go; application containers and other projects stay.
prepare_root="${temp_root}/prepare-backups"
mkdir -p "$prepare_root"
for index in 01 02 03; do
  path="${prepare_root}/202610${index}T120000Z_pre_example"
  mkdir -m 700 "$path"
  printf 'format=mudaroba-release-backup-v1\n' > "$path/release.manifest"
  printf 'postgres\n' > "$path/postgres.dump"
  printf 'qdrant\n' > "$path/qdrant.snapshot"
  printf 'env\n' > "$path/env.backup"
done
printf '%s\n' mudaroba-aibatch-b8k mudaroba-once-modq1 \
  mudaroba-migrate-run-0a1b2c3d4e5f mudaroba-celerybeat-1 other-once-x > "$FAKE_STOPPED"
: > "$FAKE_DOCKER_LOG"
prepare_args=(--project-name mudaroba --release-id "$sha_current"
  --previous-release "$sha_previous" --backup-root "$prepare_root")
FAKE_DF_AVAIL_KIB=$(( 9 * 1024 * 1024 ))
prepare_output="$(PATH="${stub_bin}:${PATH}" "${SCRIPT_DIR}/prepare-disk.sh" "${prepare_args[@]}")"
grep -F "stopped helper container: mudaroba-once-modq1" <<< "$prepare_output" >/dev/null
grep -F "candidates=2 mode=dry-run" <<< "$prepare_output" >/dev/null
[[ ! -s "$FAKE_DOCKER_LOG" ]]
[[ -d "${prepare_root}/20261001T120000Z_pre_example" ]]

PATH="${stub_bin}:${PATH}" "${SCRIPT_DIR}/prepare-disk.sh" "${prepare_args[@]}" --apply >/dev/null
[[ "$(sed -n 1p "$FAKE_DOCKER_LOG")" = "rm mudaroba-aibatch-b8k mudaroba-once-modq1 mudaroba-migrate-run-0a1b2c3d4e5f" ]]
[[ "$(sed -n 2p "$FAKE_DOCKER_LOG")" = "image rm mudaroba-backend:${sha_old} ghcr.io/mr-fulani/pharmaturk-backend:${sha_old}" ]]
[[ ! -e "${prepare_root}/20261001T120000Z_pre_example" ]]
[[ -d "${prepare_root}/20261002T120000Z_pre_example" ]]
[[ -d "${prepare_root}/20261003T120000Z_pre_example" ]]

FAKE_DF_AVAIL_KIB=$(( 3 * 1024 * 1024 ))
if PATH="${stub_bin}:${PATH}" "${SCRIPT_DIR}/prepare-disk.sh" "${prepare_args[@]}" --apply >/dev/null 2>&1; then
  printf 'prepare-disk.sh must fail when the release still does not fit\n' >&2
  exit 1
fi

printf '%s\n' "release helper tests passed"
