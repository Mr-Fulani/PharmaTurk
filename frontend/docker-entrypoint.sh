#!/bin/bash
set -e
# Ensure dependencies are installed (handles volume reuse after package.json changes)
npm install

# Next dev can keep stale server chunks between container restarts/rebuilds.
# Clear cached contents, but do not remove mounted directories themselves.
mkdir -p /app/.next /app/node_modules/.cache
find /app/.next -mindepth 1 -maxdepth 1 -exec rm -rf {} +
find /app/node_modules/.cache -mindepth 1 -maxdepth 1 -exec rm -rf {} +

exec "$@"
