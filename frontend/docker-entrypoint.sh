#!/bin/bash
set -e
# Ensure dependencies are installed (handles volume reuse after package.json changes)
npm install
exec "$@"
