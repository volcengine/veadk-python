#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
SITE_PACKAGES="$ROOT_DIR/site-packages"
HOST="0.0.0.0"
PORT="${_FAAS_RUNTIME_PORT:-8000}"

if [ ! -f "$SITE_PACKAGES/.installed" ]; then
  python3 -m pip install \
    --disable-pip-version-check \
    --no-cache-dir \
    --target "$SITE_PACKAGES" \
    -r "$ROOT_DIR/requirements.txt"
  touch "$SITE_PACKAGES/.installed"
fi

export PATH="$SITE_PACKAGES/bin:$PATH"
export PYTHONPATH="$ROOT_DIR:$SITE_PACKAGES${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m uvicorn frontend.service.studio_release_server.app:app \
  --host "$HOST" \
  --port "$PORT"
