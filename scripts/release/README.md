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
snapshot:

```bash
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
migrations disabled, and runs public HTTPS smoke checks.

Use the same release SHA in staging and production. Never rebuild between them.
The current project has no registry integration, so copy/pull the exact images
to the target host and verify their OCI revision labels before deployment.

## 4. Rollback

`rollback.sh` changes only application containers and never reverses migrations.
It stops all application services before the version switch so old and new
worker/web revisions cannot run together. If a migration or background task
changed data incompatibly, keep writers stopped and restore the matching
PostgreSQL dump and Qdrant snapshot instead of attempting an untested production
reverse migration.
