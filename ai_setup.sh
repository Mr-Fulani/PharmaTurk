#!/usr/bin/env bash
# AI setup: env check, migrations, Qdrant, sync categories/templates.
# Usage: ./ai_setup.sh [--skip-migrate] [--skip-qdrant] [--skip-sync]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${SCRIPT_DIR}/backend"
SKIP_MIGRATE=false
SKIP_QDRANT=false
SKIP_SYNC=false

for arg in "$@"; do
  case "$arg" in
    --skip-migrate) SKIP_MIGRATE=true ;;
    --skip-qdrant)  SKIP_QDRANT=true ;;
    --skip-sync)    SKIP_SYNC=true ;;
  esac
done

# 1. Check environment
if [ ! -f "${SCRIPT_DIR}/.env" ]; then
  echo "Warning: .env not found in project root. AI may fail without OPENAI_API_KEY, QDRANT_HOST, etc."
  echo "Create .env from .env.example and set at least OPENAI_API_KEY."
  read -p "Continue anyway? [y/N] " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[yY]$ ]]; then
    exit 1
  fi
fi

cd "$BACKEND_DIR"

# Activate venv if present
if [ -d "venv" ] && [ -f "venv/bin/activate" ]; then
  source venv/bin/activate
elif [ -d "../.venv" ] && [ -f "../.venv/bin/activate" ]; then
  source ../.venv/bin/activate
fi

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" &>/dev/null; then
  PYTHON=python
fi

# 2. Migrations
if [ "$SKIP_MIGRATE" = false ]; then
  echo "Running migrations..."
  "$PYTHON" manage.py migrate
fi

# 3. Qdrant collections
if [ "$SKIP_QDRANT" = false ]; then
  echo "Initializing Qdrant collections..."
  "$PYTHON" manage.py init_qdrant
fi

# 4. Sync categories and templates
if [ "$SKIP_SYNC" = false ]; then
  echo "Syncing categories to Qdrant..."
  "$PYTHON" manage.py sync_categories
  echo "Importing AI templates..."
  "$PYTHON" manage.py import_templates
fi

echo ""
echo "--- AI setup done ---"
echo "First run options:"
echo "  1. Benchmark (no queue): $PYTHON manage.py benchmark_ai"
echo "  2. Via API (needs celery_ai): POST /api/ai/process/<product_id>/ with JWT"
echo "See AI_QUICK_TEST.md for details."
