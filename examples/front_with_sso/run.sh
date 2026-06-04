#!/usr/bin/env bash
# Launch `veadk frontend` with a GitHub SSO login, configured via env vars.
# Fill in your GitHub OAuth app's client id/secret, then: bash run.sh
#
# GitHub OAuth app setup: https://github.com/settings/developers -> New OAuth App
#   Authorization callback URL must equal $OAUTH2_REDIRECT_URI below.
set -euo pipefail

export OAUTH2_PROVIDER="${OAUTH2_PROVIDER:-github}"
export OAUTH2_CLIENT_ID="${OAUTH2_CLIENT_ID:-REPLACE_ME}"
export OAUTH2_CLIENT_SECRET="${OAUTH2_CLIENT_SECRET:-REPLACE_ME}"
export OAUTH2_REDIRECT_URI="${OAUTH2_REDIRECT_URI:-http://127.0.0.1:8000/oauth2/callback}"

if [ "$OAUTH2_CLIENT_ID" = "REPLACE_ME" ]; then
  echo "Set OAUTH2_CLIENT_ID / OAUTH2_CLIENT_SECRET first (see README.md)." >&2
  exit 1
fi

# Run from the repo root so this example is one of the selectable agents.
cd "$(dirname "$0")/../.."
exec veadk frontend --agents-dir examples --host 127.0.0.1 --port 8000
