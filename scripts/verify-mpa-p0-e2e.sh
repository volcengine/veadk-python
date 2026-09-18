#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -n "${PYTHON:-}" ]; then
  PYTHON_BIN=$PYTHON
elif [ -x "$SCRIPT_DIR/../.venv/bin/python" ]; then
  PYTHON_BIN="$SCRIPT_DIR/../.venv/bin/python"
else
  PYTHON_BIN=python3
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/mpa_p0_e2e.py" "$@"
