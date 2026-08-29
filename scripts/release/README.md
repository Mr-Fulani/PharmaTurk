# Safe release workflow

These scripts separate verification, schema changes, application rollout and
rollback. They never print `.env` and use explicit Compose project names.

## 1. Local verification

For work in progress only, use a clearly non-deployable tag:

```bash
./scripts/release/predeploy.sh \
  --environment local \
  --release-id audit-$(git rev-parse --short HEAD) \
  --allow-dirty

./scripts/release/local-smoke.sh \
  --release-id audit-$(git rev-parse --short HEAD)
```

The smoke script creates a uniquely named Compose project, exposes only a
loopback high port and removes only its own containers and volumes on exit.

## 2. Releasable artifact

Review the complete diff, rotate exposed credentials, commit, and obtain a
green CI run. Staging/production tooling accepts only a clean working tree and
the exact 40-character `git rev-parse HEAD` value. Run predeploy again with
`--environment staging` and no `--allow-dirty`.

Before deployment, create and validate an external PostgreSQL dump and Qdrant
snapshot. On the Compose host, prefer the all-in-one command; it uses Qdrant's
official full-storage snapshot (all live collections), removes only the temporary
snapshot it created, copies the protected `.env`, and prints the new backup directory:

```bash
./scripts/release/create-backup.sh \
  --project-name mudaroba \
  --previous-release PREVIOUS_FULL_GIT_SHA \
  --backup-root /secure/backups/pharmaturk
```

The lower-level manifest command remains available for backups created by an
external platform:

```bash
./scripts/release/prepare-backup-manifest.sh \
  --postgres-dump /secure/backups/postgres.dump \
  --qdrant-snapshot /secure/backups/qdrant.snapshot \
  --previous-release PREVIOUS_FULL_GIT_SHA \
  --output /secure/backups/release.manifest
```

Backup retention is always a separate operation and defaults to dry-run. Review
the exact candidates before using the destructive mode. Keep the current
pre-deploy backup protected until its observation and rollback window closes.
The validator accepts both current backup names and the historical
`manifest.env`/`env.production` layout, but never treats incomplete directories
or loose files as deletion candidates:

```bash
./scripts/release/prune-backups.sh \
  --backup-root /secure/backups/pharmaturk \
  --keep 7 \
  --protect /secure/backups/pharmaturk/CURRENT_PREDEPLOY_BACKUP

./scripts/release/prune-backups.sh \
  --backup-root /secure/backups/pharmaturk \
  --keep 7 \
  --protect /secure/backups/pharmaturk/CURRENT_PREDEPLOY_BACKUP \
  --apply \
  --confirm "PRUNE BACKUPS /secure/backups/pharmaturk"
```

If the host has no PostgreSQL client installed, validate through the already
running database container without exposing a port or password:

```bash
PG_RESTORE_CONTAINER=mudaroba-postgres-1 \
  ./scripts/release/prepare-backup-manifest.sh \
  --postgres-dump /secure/backups/postgres.dump \
  --qdrant-snapshot /secure/backups/qdrant.snapshot \
  --previous-release PREVIOUS_FULL_GIT_SHA \
  --output /secure/backups/release.manifest
```

## 3. Staging, then production

`deploy.sh` requires an exact confirmation string, an explicit Compose project,
both new and previous SHA-labelled images and the validated backup manifest. It
prints the migration plan, stops Nginx/web/workers for a controlled maintenance
window, starts data services without deleting volumes, applies committed
migrations once, starts all application services on one SHA with automatic
migrations disabled, and runs public HTTPS smoke checks. Existing PostgreSQL,
Redis, and Qdrant containers are never recreated by the deploy script; state
service upgrades are a separate, explicitly planned maintenance operation.
Migration one-shots and application startup disable implicit dependency
creation, and startup waits for the backend health check before public smoke.

Use the same release SHA in staging and production. Never rebuild between them.
After all CI gates pass on `main`, the image job publishes only immutable SHA
tags to GHCR. It never publishes or moves a `latest` tag. Pull and verify those
exact images on the target host before deployment:

```bash
./scripts/release/pull-images.sh --release-id FULL_GIT_SHA
```

The GHCR packages must be public for an unauthenticated production pull, or the
operator must run `docker login ghcr.io` with a read-only package token first.
The pull script verifies the OCI revision labels and the non-root runtime users
before creating the local `mudaroba-*:<SHA>` tags required by Compose.

## 4. Rollback

`rollback.sh` changes only application containers and never reverses migrations.
It stops all application services before the version switch so old and new
worker/web revisions cannot run together. If a migration or background task
changed data incompatibly, keep writers stopped and restore the matching
PostgreSQL dump and Qdrant snapshot instead of attempting an untested production
reverse migration.
