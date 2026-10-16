#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "usage: $0 IMAGE[:TAG] [--push]" >&2
    exit 2
fi
image="$1"
output="--load"
if [[ $# == 2 ]]; then
    if [[ "$2" != "--push" ]]; then
        echo "unknown option: $2" >&2
        exit 2
    fi
    output="--push"
fi

PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.org/simple}"
UV_DEFAULT_INDEX="${UV_DEFAULT_INDEX:-${UV_INDEX_URL:-$PIP_INDEX_URL}}"

# Build arguments can survive in image/build metadata. Do not pass credentials.
PIP_INDEX_URL="$PIP_INDEX_URL" UV_DEFAULT_INDEX="$UV_DEFAULT_INDEX" python3 - <<'PY'
import os
import sys
from urllib.parse import urlsplit

for name in ("PIP_INDEX_URL", "UV_DEFAULT_INDEX"):
    try:
        value = urlsplit(os.environ[name])
        valid = (
            value.scheme in {"http", "https"}
            and value.hostname
            and not value.username
            and not value.password
            and not value.query
            and not value.fragment
        )
    except ValueError:
        valid = False
    if not valid:
        sys.exit("Package indexes must be HTTP(S) URLs without credentials, query strings or fragments")
PY

exec docker buildx build --platform "${MANAGED_AGENTS_PLATFORM:-linux/amd64}" \
    "$output" --file "$SCRIPT_DIR/Dockerfile.worker" --tag "$image" \
    --build-arg PIP_INDEX_URL="$PIP_INDEX_URL" \
    --build-arg UV_DEFAULT_INDEX="$UV_DEFAULT_INDEX" \
    "$REPO_ROOT"
