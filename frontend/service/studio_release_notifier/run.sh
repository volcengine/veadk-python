#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD:$PWD/site-packages${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m uvicorn frontend.service.studio_release_notifier.app:app --host 0.0.0.0 --port "${_FAAS_RUNTIME_PORT:-8000}"
