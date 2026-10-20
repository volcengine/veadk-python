#!/bin/sh
set -eu

if [ "${APP_ENV:-}" != "test" ] || [ "${VEADK_MPA_TEST_SCENARIOS:-}" != "1" ]; then
  echo "browser fixture requires APP_ENV=test and VEADK_MPA_TEST_SCENARIOS=1" >&2
  exit 2
fi
if [ -z "${VEADK_MPA_SCENARIO_TOKEN_FILE:-}" ]; then
  echo "VEADK_MPA_SCENARIO_TOKEN_FILE is required" >&2
  exit 2
fi
if [ ! -f "$VEADK_MPA_SCENARIO_TOKEN_FILE" ]; then
  echo "scenario token file does not exist" >&2
  exit 2
fi
case "${VEADK_MPA_FIXTURE_HOST:-127.0.0.1}" in
  127.0.0.1|::1|localhost) ;;
  *) echo "browser fixture host must be loopback" >&2; exit 2 ;;
esac

cleanup() {
  rm -f -- "$VEADK_MPA_SCENARIO_TOKEN_FILE"
}
trap cleanup EXIT HUP INT TERM

uv run veadk studio --host "${VEADK_MPA_FIXTURE_HOST:-127.0.0.1}" "$@"
