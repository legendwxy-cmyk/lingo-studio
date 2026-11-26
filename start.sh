#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[1/2] Building frontend production bundle..."
(cd "$ROOT_DIR/frontend" && npm run build)

echo "[2/2] Starting Lingo (FastAPI + built SPA) on http://0.0.0.0:8000 ..."
cd "$ROOT_DIR/backend"
exec "$ROOT_DIR/backend/.venv/bin/uvicorn" main:app --host 0.0.0.0 --port 8000
