#!/usr/bin/env bash
set -u

output_dir="${AGENTKIT_MIGRATE_OUTPUT_DIR:?AGENTKIT_MIGRATE_OUTPUT_DIR is required}"
input_dir="${AGENTKIT_MIGRATE_INPUT_DIR:-}"
asset_dir="${AGENTKIT_MIGRATE_ASSET_DIR:-}"

cd "$output_dir" || exit 1
rm -f migrate_status.md
rm -f source_capabilities.json

record_python="$(command -v python3 || command -v python || true)"
python_bin="/home/gem/venv_veadk/bin/python"
[ -x "$python_bin" ] || python_bin="$record_python"

validation_tmp_parent="${TMPDIR:-/tmp}"
validation_tmp_dir="$(mktemp -d "${validation_tmp_parent%/}/agentkit-migrate-validation.XXXXXX")" || exit 1
cleanup_validation_tmp() {
  rm -rf "$validation_tmp_dir"
}
trap cleanup_validation_tmp EXIT

checks_file="$validation_tmp_dir/checks.jsonl"
source_capabilities_file="$validation_tmp_dir/source_capabilities.json"
findings_file="$output_dir/validation_findings.json"
decision_file="$validation_tmp_dir/decision.json"
: > "$checks_file"
rm -f "$source_capabilities_file"
rm -f "$findings_file" "$decision_file"
failed=0

yaml_scalar() {
  key="$1"
  sed -n "s/^${key}:[[:space:]]*//p" .agentkit/agentkit.yaml | head -1 | sed 's/^"//; s/"$//'
}

volcengine_python_base_image="agentkit-prod-public-cn-beijing.cr.volces.com/base/py-simple:python3.12-bookworm-slim-latest"
byteplus_python_base_image="agentkit-prod-public-ap-southeast-1.cr.bytepluses.com/base/py-simple:python3.12-bookworm-slim-latest"

python_base_image_for_provider() {
  case "$1" in
    volcengine)
      printf '%s\n' "$volcengine_python_base_image"
      ;;
    byteplus)
      printf '%s\n' "$byteplus_python_base_image"
      ;;
    *)
      return 1
      ;;
  esac
}

record_check() {
  name="$1"
  status="$2"
  detail="$3"
  if [ -z "$record_python" ]; then
    printf '{"name":"%s","status":"%s","detail":"%s"}\n' "$name" "$status" "$detail" >> "$checks_file"
    return
  fi
  "$record_python" - "$checks_file" "$name" "$status" "$detail" <<'PY'
import json
import sys

path, name, status, detail = sys.argv[1:5]
with open(path, "a", encoding="utf-8") as f:
    f.write(json.dumps({"name": name, "status": status, "detail": detail}, ensure_ascii=False) + "\n")
PY
}

require_file() {
  path="$1"
  if [ -f "$path" ]; then
    record_check "file:$path" "passed" "exists"
  else
    record_check "file:$path" "failed" "missing"
    failed=1
  fi
}

for f in assistant/__init__.py assistant/agent.py main.py requirements.txt Dockerfile .agentkit/agentkit.yaml .env.example migration_plan.md source_behavior_contract.json migration_metadata.json convert_report.md eval/cases.json eval/rubric.md; do
  require_file "$f"
done

if [ -z "$python_bin" ]; then
  record_check "python" "failed" "python executable not found"
  failed=1
else
  if "$python_bin" -m compileall -q . >"$validation_tmp_dir"/agentkit-migrate-compile.log 2>&1; then
    record_check "compileall" "passed" "python files compile"
  else
    record_check "compileall" "failed" "$(tail -20 "$validation_tmp_dir"/agentkit-migrate-compile.log | tr '\n' ' ')"
    failed=1
  fi

  if PYTHONPATH="$output_dir" "$python_bin" - <<'PY' >"$validation_tmp_dir"/agentkit-migrate-import.log 2>&1
from assistant.agent import root_agent
print(getattr(root_agent, "name", type(root_agent).__name__))
PY
  then
    record_check "import:assistant.agent.root_agent" "passed" "$(tail -1 "$validation_tmp_dir"/agentkit-migrate-import.log)"
  else
    record_check "import:assistant.agent.root_agent" "failed" "$(tail -20 "$validation_tmp_dir"/agentkit-migrate-import.log | tr '\n' ' ')"
    failed=1
  fi

  if PYTHONPATH="$output_dir" "$python_bin" - <<'PY' >"$validation_tmp_dir"/agentkit-migrate-main.log 2>&1
from main import app
print(type(app).__name__)
PY
  then
    record_check "import:main.app" "passed" "$(tail -1 "$validation_tmp_dir"/agentkit-migrate-main.log)"
  else
    record_check "import:main.app" "failed" "$(tail -20 "$validation_tmp_dir"/agentkit-migrate-main.log | tr '\n' ' ')"
    failed=1
  fi
fi

if grep -q '^veadk-python' requirements.txt && grep -q '^agentkit-sdk-python' requirements.txt; then
  record_check "requirements:platform" "passed" "contains veadk-python and agentkit-sdk-python"
else
  record_check "requirements:platform" "failed" "missing veadk-python or agentkit-sdk-python"
  failed=1
fi

if grep -q 'AgentkitAgentServerApp' main.py && grep -q 'app' main.py; then
  record_check "main:agentkit_server_app" "passed" "main.py exposes AgentkitAgentServerApp app"
else
  record_check "main:agentkit_server_app" "failed" "main.py does not expose AgentkitAgentServerApp app"
  failed=1
fi

if grep -Eq '^apmplus:[[:space:]]+true[[:space:]]*$' .agentkit/agentkit.yaml; then
  record_check "observability:platform_apmplus" "passed" ".agentkit/agentkit.yaml enables top-level platform APMPlus by default"
else
  record_check "observability:platform_apmplus" "failed" ".agentkit/agentkit.yaml must include top-level apmplus: true for migrated AgentKit runtimes"
  failed=1
fi

expected_target_project="${AGENTKIT_TARGET_PROJECT-default}"
actual_target_project="$(yaml_scalar "project")"
if [ "$actual_target_project" = "$expected_target_project" ]; then
  record_check "cli_contract:project" "passed" ".agentkit/agentkit.yaml preserves target project ${expected_target_project}"
else
  record_check "cli_contract:project" "failed" ".agentkit/agentkit.yaml must preserve AGENTKIT_TARGET_PROJECT as project: ${expected_target_project}"
  failed=1
fi

expected_cloud_provider="${AGENTKIT_TARGET_CLOUD_PROVIDER:-${AGENTKIT_CLOUD_PROVIDER:-${CLOUD_PROVIDER:-}}}"
expected_cloud_provider="$(printf '%s' "$expected_cloud_provider" | tr '[:upper:]' '[:lower:]')"
if [ -n "$expected_cloud_provider" ]; then
  actual_cloud_provider="$(yaml_scalar "cloud_provider" | tr '[:upper:]' '[:lower:]')"
  if [ "$actual_cloud_provider" = "$expected_cloud_provider" ]; then
    record_check "cli_contract:cloud_provider" "passed" ".agentkit/agentkit.yaml preserves target cloud provider ${expected_cloud_provider}"
  else
    record_check "cli_contract:cloud_provider" "failed" ".agentkit/agentkit.yaml must preserve target cloud_provider: ${expected_cloud_provider}"
    failed=1
  fi

  if [ -f Dockerfile ]; then
    expected_python_base_image="$(python_base_image_for_provider "$expected_cloud_provider" || true)"
    if [ -n "$expected_python_base_image" ]; then
      if grep -Fq "$expected_python_base_image" Dockerfile; then
        record_check "cli_contract:dockerfile_base" "passed" "Dockerfile uses the ${expected_cloud_provider} AgentKit Python base image"
      elif grep -Fq "$volcengine_python_base_image" Dockerfile || grep -Fq "$byteplus_python_base_image" Dockerfile; then
        record_check "cli_contract:dockerfile_base" "failed" "Dockerfile uses an AgentKit Python base image for a different provider; expected ${expected_python_base_image}"
        failed=1
      else
        record_check "cli_contract:dockerfile_base" "warning" "Dockerfile uses a custom base image; provider registry pullability was not statically verified"
      fi
    fi
  fi
fi

expected_target_region="${AGENTKIT_TARGET_REGION:-}"
if [ -z "$expected_target_region" ] && [ "$expected_cloud_provider" = "byteplus" ]; then
  expected_target_region="${BYTEPLUS_REGION:-ap-southeast-1}"
elif [ -z "$expected_target_region" ] && [ "$expected_cloud_provider" = "volcengine" ]; then
  expected_target_region="${VOLCENGINE_REGION:-${VOLC_REGION:-cn-beijing}}"
fi
if [ -n "$expected_target_region" ]; then
  actual_target_region="$(yaml_scalar "region")"
  if [ "$actual_target_region" = "$expected_target_region" ]; then
    record_check "cli_contract:region" "passed" ".agentkit/agentkit.yaml preserves target region ${expected_target_region}"
  else
    record_check "cli_contract:region" "failed" ".agentkit/agentkit.yaml must preserve target region: ${expected_target_region}"
    failed=1
  fi
fi

expected_app_name="${AGENTKIT_MIGRATE_APP_NAME:-}"
expected_project_name=""
if [ -n "$expected_app_name" ]; then
  expected_project_name="$(printf '%s' "$expected_app_name" | tr -c 'A-Za-z0-9_-' '-' | sed 's/^-*//; s/-*$//')"
  [ -n "$expected_project_name" ] || expected_project_name="agentkit_migrated"
  if grep -Eq "^name:[[:space:]]+${expected_project_name}[[:space:]]*$" .agentkit/agentkit.yaml; then
    record_check "cli_contract:app_name" "passed" ".agentkit/agentkit.yaml preserves --name ${expected_project_name}"
  else
    record_check "cli_contract:app_name" "failed" ".agentkit/agentkit.yaml must preserve AGENTKIT_MIGRATE_APP_NAME/--name as name: ${expected_project_name}"
    failed=1
  fi
fi

stale_files=()
[ -f agentkit.yaml ] && stale_files+=("agentkit.yaml")
[ -f agent.py ] && stale_files+=("agent.py")
[ -f agentkit_migrated.py ] && stale_files+=("agentkit_migrated.py")
[ -n "$expected_project_name" ] && [ -f "${expected_project_name}.py" ] && stale_files+=("${expected_project_name}.py")
if [ "${#stale_files[@]}" -eq 0 ]; then
  record_check "artifact_hygiene:no_legacy_init_files" "passed" "no legacy agentkit init root config, root agent shim, or SimpleApp entrypoint remains"
else
  record_check "artifact_hygiene:no_legacy_init_files" "failed" "remove legacy agentkit init files: ${stale_files[*]}"
  failed=1
fi

intermediate_artifacts=()
[ -f source_capabilities.json ] && intermediate_artifacts+=("source_capabilities.json")
[ -d .codex ] && intermediate_artifacts+=(".codex/")
[ -d .agentkit/migrate ] && intermediate_artifacts+=(".agentkit/migrate/")
[ -d .agentkit/artifacts ] && intermediate_artifacts+=(".agentkit/artifacts/")
[ -d .pytest_cache ] && intermediate_artifacts+=(".pytest_cache/")
find . -type f -name '*.pyc' -delete
find . -type d -name __pycache__ -prune -exec rm -rf {} +
if find . -type d -name __pycache__ -print -quit | grep -q .; then
  intermediate_artifacts+=("__pycache__/")
fi
if find . -type f -name '*.pyc' -print -quit | grep -q .; then
  intermediate_artifacts+=("*.pyc")
fi
if [ "${#intermediate_artifacts[@]}" -eq 0 ]; then
  record_check "artifact_hygiene:no_migration_intermediates" "passed" "no migration-only detector, cache, or deploy artifact directories remain"
else
  record_check "artifact_hygiene:no_migration_intermediates" "failed" "remove migration-only artifacts: ${intermediate_artifacts[*]}"
  failed=1
fi

if [ -f .dockerignore ] \
  && grep -qxF 'source_capabilities.json' .dockerignore \
  && grep -qxF 'source_behavior_contract.json' .dockerignore \
  && grep -qxF 'migration_metadata.json' .dockerignore \
  && grep -qxF 'migration_plan.md' .dockerignore \
  && grep -qxF 'convert_report.md' .dockerignore \
  && grep -qxF 'eval/' .dockerignore; then
  record_check "artifact_hygiene:dockerignore_non_runtime_files" "passed" ".dockerignore excludes migration audit, behavior contract, and eval files from runtime image"
else
  record_check "artifact_hygiene:dockerignore_non_runtime_files" "failed" ".dockerignore must exclude source_capabilities.json, source_behavior_contract.json, migration_metadata.json, migration_plan.md, convert_report.md, and eval/"
  failed=1
fi

expected_key_env="${AGENTKIT_TARGET_MODEL_API_KEY_ENV:-MODEL_AGENT_API_KEY}"
if grep -Fq -- "$expected_key_env" .agentkit/agentkit.yaml && grep -Fq -- "${expected_key_env}=" .env.example; then
  record_check "cli_contract:model_api_key_env" "passed" "generated config preserves target model API key env ${expected_key_env}"
else
  record_check "cli_contract:model_api_key_env" "failed" ".agentkit/agentkit.yaml and .env.example must preserve target model API key env ${expected_key_env}"
  failed=1
fi

if grep -Fq -- "$expected_key_env" assistant/agent.py; then
  record_check "cli_contract:model_api_key_agent" "passed" "assistant/agent.py reads target model API key env ${expected_key_env}"
else
  record_check "cli_contract:model_api_key_agent" "failed" "assistant/agent.py must read AGENTKIT_TARGET_MODEL_API_KEY_ENV (${expected_key_env}) for the model API key"
  failed=1
fi

if [ "$expected_key_env" != "MODEL_AGENT_API_KEY" ] \
  && grep -Eq '^[[:space:]]+MODEL_AGENT_API_KEY:[[:space:]]+\$\{MODEL_AGENT_API_KEY:-[[:space:]]*\}[[:space:]]*$' .agentkit/agentkit.yaml; then
  record_check "cli_contract:model_api_key_no_empty_alias" "failed" "do not generate an empty MODEL_AGENT_API_KEY alias when the CLI target key env is ${expected_key_env}"
  failed=1
else
  record_check "cli_contract:model_api_key_no_empty_alias" "passed" "no empty model API key alias conflicts with the target key env"
fi

if grep -Eq '^[[:space:]]+MODEL_BASE_URL:' .agentkit/agentkit.yaml || grep -Eq '^MODEL_BASE_URL=' .env.example; then
  record_check "cli_contract:model_api_base_env" "failed" "generated config must use canonical VeADK MODEL_AGENT_API_BASE; do not write legacy MODEL_BASE_URL in .agentkit/agentkit.yaml or .env.example"
  failed=1
elif grep -Fq 'MODEL_AGENT_API_BASE' assistant/agent.py; then
  record_check "cli_contract:model_api_base_env" "passed" "assistant/agent.py reads canonical VeADK MODEL_AGENT_API_BASE and may keep MODEL_BASE_URL only as a runtime compatibility fallback"
else
  record_check "cli_contract:model_api_base_env" "failed" "assistant/agent.py must read MODEL_AGENT_API_BASE for VeADK model_api_base"
  failed=1
fi

expected_model_id="${AGENTKIT_TARGET_MODEL_ID:-}"
if [ -n "$expected_model_id" ]; then
  if grep -Fq -- "$expected_model_id" .agentkit/agentkit.yaml && grep -Fq -- "$expected_model_id" .env.example && grep -Fq -- "$expected_model_id" assistant/agent.py; then
    record_check "cli_contract:model_id" "passed" "generated config and agent preserve target model id"
  else
    record_check "cli_contract:model_id" "failed" ".agentkit/agentkit.yaml, .env.example, and assistant/agent.py must preserve AGENTKIT_TARGET_MODEL_ID"
    failed=1
  fi
fi

expected_model_base_url="${AGENTKIT_TARGET_MODEL_BASE_URL:-}"
if [ -n "$expected_model_base_url" ]; then
  if grep -Eq '^[[:space:]]+MODEL_AGENT_API_BASE:' .agentkit/agentkit.yaml \
    && grep -Eq '^MODEL_AGENT_API_BASE=' .env.example \
    && grep -Fq -- "$expected_model_base_url" .agentkit/agentkit.yaml \
    && grep -Fq -- "$expected_model_base_url" .env.example \
    && grep -Fq -- "$expected_model_base_url" assistant/agent.py; then
    record_check "cli_contract:model_base_url" "passed" "generated config and agent preserve target model base URL through MODEL_AGENT_API_BASE"
  else
    record_check "cli_contract:model_base_url" "failed" ".agentkit/agentkit.yaml, .env.example, and assistant/agent.py must preserve AGENTKIT_TARGET_MODEL_BASE_URL through MODEL_AGENT_API_BASE"
    failed=1
  fi
fi

if [ -n "$record_python" ]; then
  if "$record_python" - <<'PY' >"$validation_tmp_dir"/agentkit-migrate-observability-envs.log 2>&1
import json
import re
from pathlib import Path

required_envs = [
    "ENABLE_APMPLUS",
    "ENABLE_LLM_SHIELD",
]
optional_envs = [
    "OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY",
    "OBSERVABILITY_OPENTELEMETRY_APMPLUS_ENDPOINT",
    "OBSERVABILITY_OPENTELEMETRY_APMPLUS_SERVICE_NAME",
    "TOOL_LLM_SHIELD_APP_ID",
    "TOOL_LLM_SHIELD_API_KEY",
    "TOOL_LLM_SHIELD_REGION",
]
removed_envs = [
    "OTEL_RESOURCE_ATTRIBUTES",
    "OTEL_SERVICE_NAME",
]

agentkit_yaml = Path(".agentkit/agentkit.yaml").read_text(encoding="utf-8", errors="replace")
env_example = Path(".env.example").read_text(encoding="utf-8", errors="replace")

top_level_keys = set()
env_keys = set()
current_top_key = None
env_child_indent = None
for raw_line in agentkit_yaml.splitlines():
    line_without_comment = raw_line.split("#", 1)[0].rstrip()
    if not line_without_comment.strip() or ":" not in line_without_comment:
        continue
    indent = len(raw_line) - len(raw_line.lstrip(" "))
    key = line_without_comment.split(":", 1)[0].strip().strip("'\"")
    if indent == 0:
        top_level_keys.add(key)
        current_top_key = key
        if key == "envs":
            env_child_indent = None
    elif current_top_key == "envs" and indent > 0:
        if env_child_indent is None:
            env_child_indent = indent
        if indent != env_child_indent:
            continue
        env_keys.add(key)

all_known_envs = required_envs + optional_envs

def is_default_true(text: str, env_name: str) -> bool:
    patterns = [
        rf"{re.escape(env_name)}\s*:\s*\$\{{{re.escape(env_name)}:-\s*true\s*\}}",
        rf"^{re.escape(env_name)}=true\s*$",
    ]
    return any(re.search(pattern, text, re.IGNORECASE | re.MULTILINE) for pattern in patterns)

def is_empty_optional_yaml_value(text: str, env_name: str) -> bool:
    match = re.search(rf"^\s*{re.escape(env_name)}\s*:\s*(.*)$", text, re.MULTILINE)
    if not match:
        return False
    value = match.group(1).strip().strip("'\"")
    return not value or bool(re.fullmatch(rf"\$\{{{re.escape(env_name)}:-\s*\}}", value))

def is_empty_env_example_value(text: str, env_name: str) -> bool:
    match = re.search(rf"^{re.escape(env_name)}=(.*)$", text, re.MULTILINE)
    return bool(match and not match.group(1).strip())

def top_level_bool(text: str, key: str):
    match = re.search(rf"^{re.escape(key)}:\s*(true|false)\s*$", text, re.IGNORECASE | re.MULTILINE)
    return match.group(1).lower() if match else None

apmplus_default_true = is_default_true(agentkit_yaml, "ENABLE_APMPLUS") and is_default_true(env_example, "ENABLE_APMPLUS")
apmplus_value = top_level_bool(agentkit_yaml, "apmplus")
if not apmplus_default_true:
    raise SystemExit("ENABLE_APMPLUS must default to true in .agentkit/agentkit.yaml and .env.example for migrated AgentKit runtimes")
if apmplus_value != "true":
    raise SystemExit("top-level apmplus must be true for migrated AgentKit runtimes")

misplaced = [key for key in all_known_envs if key in top_level_keys]
if misplaced:
    raise SystemExit(f"runtime env keys must be under envs, not top level: {', '.join(misplaced)}")

removed = [
    key
    for key in removed_envs
    if re.search(rf"^\s*{re.escape(key)}\s*:", agentkit_yaml, re.MULTILINE) or re.search(rf"^{re.escape(key)}=", env_example, re.MULTILINE)
]
if removed:
    raise SystemExit(f"removed OTEL envs must not be generated: {', '.join(removed)}")

missing_yaml = [key for key in required_envs if key not in env_keys]
if missing_yaml:
    raise SystemExit(f".agentkit/agentkit.yaml envs missing: {', '.join(missing_yaml)}")

missing_example = [
    key
    for key in required_envs
    if not re.search(rf"^{re.escape(key)}=", env_example, re.MULTILINE)
]
if missing_example:
    raise SystemExit(f".env.example missing: {', '.join(missing_example)}")

shield_credential_keys = ["TOOL_LLM_SHIELD_APP_ID", "TOOL_LLM_SHIELD_API_KEY"]
yaml_shield_credentials = [key for key in shield_credential_keys if key in env_keys]
example_shield_credentials = [
    key
    for key in shield_credential_keys
    if re.search(rf"^{re.escape(key)}=", env_example, re.MULTILINE)
]
for scope, present in ((".agentkit/agentkit.yaml", yaml_shield_credentials), (".env.example", example_shield_credentials)):
    if present and len(present) != len(shield_credential_keys):
        raise SystemExit(f"{scope} must define TOOL_LLM_SHIELD_APP_ID and TOOL_LLM_SHIELD_API_KEY together, or omit both")
empty_yaml_credentials = [key for key in shield_credential_keys if key in env_keys and is_empty_optional_yaml_value(agentkit_yaml, key)]
if empty_yaml_credentials:
    raise SystemExit(f".agentkit/agentkit.yaml must omit empty LLM Shield credential envs: {', '.join(empty_yaml_credentials)}")
empty_example_credentials = [key for key in shield_credential_keys if is_empty_env_example_value(env_example, key)]
if empty_example_credentials:
    raise SystemExit(f".env.example must omit empty LLM Shield credential envs: {', '.join(empty_example_credentials)}")
if is_default_true(agentkit_yaml, "ENABLE_LLM_SHIELD") and len(yaml_shield_credentials) != len(shield_credential_keys):
    raise SystemExit("ENABLE_LLM_SHIELD must default to false unless TOOL_LLM_SHIELD_APP_ID and TOOL_LLM_SHIELD_API_KEY are configured")

print(json.dumps({"agentkit_yaml_envs": sorted(env_keys & set(all_known_envs))}, ensure_ascii=False))
PY
  then
    record_check "observability:env_config" "passed" "$(tail -1 "$validation_tmp_dir"/agentkit-migrate-observability-envs.log)"
  else
    record_check "observability:env_config" "failed" "$(tail -20 "$validation_tmp_dir"/agentkit-migrate-observability-envs.log | tr '\n' ' ')"
    failed=1
  fi
else
  record_check "observability:env_config" "failed" "python executable not found; cannot validate .agentkit/agentkit.yaml env structure"
  failed=1
fi

if grep -Eq "tracers[[:space:]]*=|['\"]tracers['\"][[:space:]]*:" assistant/agent.py \
  && grep -q 'OBSERVABILITY_OPENTELEMETRY_APMPLUS' assistant/agent.py \
  && grep -q 'ENABLE_APMPLUS' assistant/agent.py; then
  record_check "observability:agent_tracing" "passed" "assistant/agent.py keeps env-gated VeADK tracer wiring"
else
  record_check "observability:agent_tracing" "failed" "assistant/agent.py must keep env-gated VeADK tracer wiring and ENABLE_APMPLUS without requiring a fixed code shape"
  failed=1
fi

if grep -q 'VOLCENGINE_ACCESS_KEY' assistant/agent.py \
  && grep -q '/var/run/secrets/iam/credential' assistant/agent.py \
  && grep -q 'APMPlusExporter()' assistant/agent.py; then
  record_check "observability:apmplus_credentials" "passed" "assistant/agent.py supports APMPlus explicit API key, Volcengine AK/SK, or VeFaaS IAM without requiring endpoint/service envs"
else
  record_check "observability:apmplus_credentials" "failed" "assistant/agent.py must allow VeADK APMPlusExporter to use explicit API key, Volcengine AK/SK, or VeFaaS IAM; do not require all OBSERVABILITY_OPENTELEMETRY_APMPLUS_* envs"
  failed=1
fi

if [ -n "$record_python" ]; then
  if "$record_python" - <<'PY' >"$validation_tmp_dir"/agentkit-migrate-guardrail-envs.log 2>&1
import re
from pathlib import Path

agentkit_yaml = Path(".agentkit/agentkit.yaml").read_text(encoding="utf-8", errors="replace")
env_example = Path(".env.example").read_text(encoding="utf-8", errors="replace")

def has_yaml_key(text: str, key: str) -> bool:
    return bool(re.search(rf"^\s*{re.escape(key)}\s*:", text, re.MULTILINE))

def has_env_key(text: str, key: str) -> bool:
    return bool(re.search(rf"^{re.escape(key)}=", text, re.MULTILINE))

def is_empty_yaml_value(text: str, key: str) -> bool:
    match = re.search(rf"^\s*{re.escape(key)}\s*:\s*(.*)$", text, re.MULTILINE)
    if not match:
        return False
    value = match.group(1).strip().strip("'\"")
    return not value or bool(re.fullmatch(rf"\$\{{{re.escape(key)}:-\s*\}}", value))

def is_empty_env_value(text: str, key: str) -> bool:
    match = re.search(rf"^{re.escape(key)}=(.*)$", text, re.MULTILINE)
    return bool(match and not match.group(1).strip())

def defaults_true(text: str, key: str) -> bool:
    return bool(
        re.search(rf"{re.escape(key)}\s*:\s*\$\{{{re.escape(key)}:-\s*true\s*\}}", text, re.IGNORECASE | re.MULTILINE)
        or re.search(rf"^{re.escape(key)}=true\s*$", text, re.IGNORECASE | re.MULTILINE)
    )

credential_keys = ["TOOL_LLM_SHIELD_APP_ID", "TOOL_LLM_SHIELD_API_KEY"]
if not has_yaml_key(agentkit_yaml, "ENABLE_LLM_SHIELD") or not has_env_key(env_example, "ENABLE_LLM_SHIELD"):
    raise SystemExit("ENABLE_LLM_SHIELD must be documented in .agentkit/agentkit.yaml and .env.example")
for source_name, text, has_key in (
    (".agentkit/agentkit.yaml", agentkit_yaml, has_yaml_key),
    (".env.example", env_example, has_env_key),
):
    present = [key for key in credential_keys if has_key(text, key)]
    if present and len(present) != len(credential_keys):
        raise SystemExit(f"{source_name} must define TOOL_LLM_SHIELD_APP_ID and TOOL_LLM_SHIELD_API_KEY together, or omit both")
if any(is_empty_yaml_value(agentkit_yaml, key) for key in credential_keys):
    raise SystemExit(".agentkit/agentkit.yaml must omit empty LLM Shield credential envs")
if any(is_empty_env_value(env_example, key) for key in credential_keys):
    raise SystemExit(".env.example must omit empty LLM Shield credential envs")
if defaults_true(agentkit_yaml, "ENABLE_LLM_SHIELD") and not all(has_yaml_key(agentkit_yaml, key) for key in credential_keys):
    raise SystemExit("ENABLE_LLM_SHIELD must default to false unless LLM Shield credentials are configured")
print("LLM Shield switch is present and optional credentials are clean")
PY
  then
    record_check "guardrails:env_config" "passed" "$(tail -1 "$validation_tmp_dir"/agentkit-migrate-guardrail-envs.log)"
  else
    record_check "guardrails:env_config" "failed" "$(tail -20 "$validation_tmp_dir"/agentkit-migrate-guardrail-envs.log | tr '\n' ' ')"
    failed=1
  fi
else
  record_check "guardrails:env_config" "failed" "python executable not found; cannot validate LLM Shield env structure"
  failed=1
fi

if grep -q 'ENABLE_LLM_SHIELD' assistant/agent.py \
  && grep -q 'before_model_callback' assistant/agent.py \
  && grep -q 'before_tool_callback' assistant/agent.py; then
  record_check "guardrails:llm_shield_callbacks" "passed" "assistant/agent.py keeps env-gated VeADK LLM Shield callback wiring"
else
  record_check "guardrails:llm_shield_callbacks" "failed" "assistant/agent.py must keep env-gated VeADK LLM Shield callbacks for model and tool boundaries"
  failed=1
fi

if find skills -mindepth 2 -maxdepth 2 -name SKILL.md -print -quit 2>/dev/null | grep -q .; then
  if grep -q 'load_skill_from_dir' assistant/agent.py && grep -q 'SkillToolset' assistant/agent.py; then
    record_check "skills:adk_toolset_wiring" "passed" "generated local skills are mounted through ADK load_skill_from_dir and SkillToolset"
  else
    record_check "skills:adk_toolset_wiring" "warning" "best-effort source skill migration did not mount generated local skills through ADK load_skill_from_dir and SkillToolset; report this limitation or fix it when behavior preservation depends on skills"
  fi

  if [ -n "$python_bin" ]; then
    if "$python_bin" - <<'PY' >"$validation_tmp_dir"/agentkit-migrate-skills.log 2>&1
from pathlib import Path

root = Path(".")
skill_dirs = sorted(path.parent for path in (root / "skills").glob("*/SKILL.md"))
if not skill_dirs:
    raise SystemExit("no generated skills found")

from google.adk.skills import load_skill_from_dir

loaded = []
for skill_dir in skill_dirs:
    skill = load_skill_from_dir(skill_dir)
    loaded.append(skill.name)
print(",".join(loaded))
PY
    then
      record_check "skills:adk_loadable" "passed" "$(tail -1 "$validation_tmp_dir"/agentkit-migrate-skills.log)"
    else
      record_check "skills:adk_loadable" "warning" "$(tail -20 "$validation_tmp_dir"/agentkit-migrate-skills.log | tr '\n' ' ')"
    fi
  else
    record_check "skills:adk_loadable" "warning" "python executable not found; cannot validate generated ADK skill packages"
  fi

  skill_creator_validator=""
  skill_root="${AGENTKIT_MIGRATE_SKILL_PATH:-}"
  home_dir="${HOME:-}"
  for candidate in \
    "$skill_root/.system/skill-creator/scripts/quick_validate.py" \
    "$skill_root/skill-creator/scripts/quick_validate.py" \
    "$home_dir/.codex/skills/.system/skill-creator/scripts/quick_validate.py" \
    "$home_dir/.codex/skills/skill-creator/scripts/quick_validate.py"; do
    [ -n "$candidate" ] || continue
    if [ -f "$candidate" ]; then
      skill_creator_validator="$candidate"
      break
    fi
  done
  if [ -n "$skill_creator_validator" ] && [ -n "$python_bin" ]; then
    skill_creator_status=0
    : > "$validation_tmp_dir"/agentkit-migrate-skill-creator-validate.log
    while IFS= read -r skill_md; do
      skill_dir="$(dirname "$skill_md")"
      printf '== %s ==\n' "$skill_dir" >> "$validation_tmp_dir"/agentkit-migrate-skill-creator-validate.log
      if ! "$python_bin" "$skill_creator_validator" "$skill_dir" >> "$validation_tmp_dir"/agentkit-migrate-skill-creator-validate.log 2>&1; then
        skill_creator_status=1
      fi
    done < <(find skills -mindepth 2 -maxdepth 2 -name SKILL.md -print 2>/dev/null | sort)
    if [ "$skill_creator_status" -eq 0 ]; then
      record_check "skills:skill_creator_quick_validate" "passed" "skill-creator quick_validate.py accepted generated skills without rewriting them"
    else
      record_check "skills:skill_creator_quick_validate" "warning" "$(tail -40 "$validation_tmp_dir"/agentkit-migrate-skill-creator-validate.log | tr '\n' ' ')"
    fi
  else
    record_check "skills:skill_creator_quick_validate" "warning" "skill-creator quick_validate.py not available; skipped read-only generated skill validation"
  fi
fi

if [ -n "$record_python" ] && [ -n "$input_dir" ] && [ -n "$asset_dir" ] && [ -d "$input_dir" ]; then
  detector="$asset_dir/scripts/detect_source_capabilities.py"
  if [ -f "$detector" ]; then
    if "$record_python" "$detector" "$input_dir" "$source_capabilities_file" >"$validation_tmp_dir"/agentkit-migrate-detect-source.log 2>&1; then
      record_check "source_detection:capabilities" "passed" "source observability and guardrail signals detected into migration metadata"
    else
      record_check "source_detection:capabilities" "failed" "$(tail -20 "$validation_tmp_dir"/agentkit-migrate-detect-source.log | tr '\n' ' ')"
      failed=1
    fi
  else
    record_check "source_detection:capabilities" "failed" "missing source capability detector at $detector"
    failed=1
  fi
fi

if [ -s "$source_capabilities_file" ] && [ -n "$record_python" ]; then
  if "$record_python" - "$source_capabilities_file" <<'PY' >"$validation_tmp_dir"/agentkit-migrate-source-skills.log 2>&1
import json
import sys
from pathlib import Path

capabilities = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
source_skills = capabilities.get("skills", {}).get("items", [])
generated_skills = sorted(Path("skills").glob("*/SKILL.md"))
if source_skills and not generated_skills:
    names = ", ".join(str(item.get("name") or item.get("path")) for item in source_skills[:5] if isinstance(item, dict))
    print(f"warning: source business skills were detected but no generated skills/*/SKILL.md packages were found: {names}")
    raise SystemExit(3)
print(f"source_skills={len(source_skills)} generated_skills={len(generated_skills)}")
PY
  then
    record_check "skills:source_materialized" "passed" "$(tail -1 "$validation_tmp_dir"/agentkit-migrate-source-skills.log)"
  else
    record_check "skills:source_materialized" "warning" "$(tail -20 "$validation_tmp_dir"/agentkit-migrate-source-skills.log | tr '\n' ' ')"
  fi
fi

if [ -s "$source_capabilities_file" ] && [ -n "$record_python" ]; then
  if "$record_python" - "$source_capabilities_file" <<'PY' >"$validation_tmp_dir"/agentkit-migrate-source-defaults.log 2>&1
import json
import re
import sys
from pathlib import Path

capabilities = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
agentkit_yaml = Path(".agentkit/agentkit.yaml").read_text(encoding="utf-8", errors="replace")
env_example = Path(".env.example").read_text(encoding="utf-8", errors="replace")
agent_py = Path("assistant/agent.py").read_text(encoding="utf-8", errors="replace")

def has_default_true(text: str, env_name: str) -> bool:
    patterns = [
        rf"{re.escape(env_name)}\s*:\s*\$\{{{re.escape(env_name)}:-true\}}",
        rf"^{re.escape(env_name)}=true\s*$",
        rf'{re.escape(env_name)}["\']?\s*,\s*["\']true["\']',
    ]
    return any(re.search(pattern, text, re.IGNORECASE | re.MULTILINE) for pattern in patterns)

def has_default_false(text: str, env_name: str) -> bool:
    patterns = [
        rf"{re.escape(env_name)}\s*:\s*\$\{{{re.escape(env_name)}:-false\}}",
        rf"^{re.escape(env_name)}=false\s*$",
        rf'{re.escape(env_name)}["\']?\s*,\s*["\']false["\']',
    ]
    return any(re.search(pattern, text, re.IGNORECASE | re.MULTILINE) for pattern in patterns)

def has_yaml_key(text: str, env_name: str) -> bool:
    return bool(re.search(rf"^\s*{re.escape(env_name)}\s*:", text, re.MULTILINE))

observability_default_enabled = bool(capabilities.get("observability", {}).get("default_enable_apmplus"))
guardrails_default_enabled = bool(capabilities.get("guardrails", {}).get("default_enable_llm_shield"))
if not observability_default_enabled:
    raise SystemExit("migrated AgentKit runtimes must default APMPlus observability to enabled")
if not (has_default_true(agentkit_yaml, "ENABLE_APMPLUS") and has_default_true(env_example, "ENABLE_APMPLUS") and has_default_true(agent_py, "ENABLE_APMPLUS")):
    raise SystemExit("ENABLE_APMPLUS must default to true in agentkit.yaml, .env.example, and assistant/agent.py")
if not re.search(r"^apmplus:\s*true\s*$", agentkit_yaml, re.IGNORECASE | re.MULTILINE):
    raise SystemExit("top-level apmplus must be true")
llm_shield_credentials_configured = has_yaml_key(agentkit_yaml, "TOOL_LLM_SHIELD_APP_ID") and has_yaml_key(agentkit_yaml, "TOOL_LLM_SHIELD_API_KEY")
if guardrails_default_enabled and llm_shield_credentials_configured:
    if not (has_default_true(agentkit_yaml, "ENABLE_LLM_SHIELD") and has_default_true(env_example, "ENABLE_LLM_SHIELD") and has_default_true(agent_py, "ENABLE_LLM_SHIELD")):
        raise SystemExit("source has guardrail/safety signals; ENABLE_LLM_SHIELD must default to true in agentkit.yaml, .env.example, and assistant/agent.py")
if guardrails_default_enabled and not llm_shield_credentials_configured:
    if not (has_default_false(agentkit_yaml, "ENABLE_LLM_SHIELD") and has_default_false(env_example, "ENABLE_LLM_SHIELD") and has_default_false(agent_py, "ENABLE_LLM_SHIELD")):
        raise SystemExit("source has guardrail/safety signals but LLM Shield credentials are missing; ENABLE_LLM_SHIELD must default to false")
print(json.dumps({"observability_default_enabled": observability_default_enabled, "guardrails_default_enabled": guardrails_default_enabled, "llm_shield_credentials_configured": llm_shield_credentials_configured}, ensure_ascii=False))
PY
  then
    record_check "source_detection:default_switches" "passed" "$(tail -1 "$validation_tmp_dir"/agentkit-migrate-source-defaults.log)"
  else
    record_check "source_detection:default_switches" "failed" "$(tail -20 "$validation_tmp_dir"/agentkit-migrate-source-defaults.log | tr '\n' ' ')"
    failed=1
  fi
fi

if [ -n "$python_bin" ]; then
  if "$python_bin" - <<'PY' >"$validation_tmp_dir"/agentkit-migrate-placeholder.log 2>&1
import json
from pathlib import Path

agent_text = Path("assistant/agent.py").read_text(encoding="utf-8", errors="replace")
plan_text = Path("migration_plan.md").read_text(encoding="utf-8", errors="replace")
metadata_path = Path("migration_metadata.json")
contract_path = Path("source_behavior_contract.json")
try:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
except Exception:
    metadata = {}
try:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
except Exception:
    contract = {}

sentinels = [
    "The migration will replace this placeholder with source-specific behavior.",
    "Migrated AgentKit Runtime agent.",
    "Bootstrap completed. Source analysis, behavior mapping, implementation, and validation are pending.",
    "pending_source_analysis",
]
if any(s in agent_text for s in sentinels[:2]):
    raise SystemExit("assistant/agent.py still contains bootstrap agent sentinel")
if sentinels[2] in plan_text:
    raise SystemExit("migration_plan.md still contains bootstrap plan sentinel")
if metadata.get("source") == "pending_analysis" or metadata.get("status") == "bootstrapped":
    raise SystemExit("migration_metadata.json still reports pending bootstrap analysis")
if json.dumps(contract, ensure_ascii=False).find("pending_source_analysis") >= 0:
    raise SystemExit("source_behavior_contract.json still contains pending bootstrap analysis")
PY
  then
    record_check "migration:not_placeholder" "passed" "bootstrap sentinels were replaced"
  else
    record_check "migration:not_placeholder" "failed" "$(tail -20 "$validation_tmp_dir"/agentkit-migrate-placeholder.log | tr '\n' ' ')"
    failed=1
  fi
fi

if [ -n "$python_bin" ]; then
  if "$python_bin" - <<'PY' >"$validation_tmp_dir"/agentkit-migrate-behavior-contract.log 2>&1
import json
from pathlib import Path

path = Path("source_behavior_contract.json")
contract = json.loads(path.read_text(encoding="utf-8"))
if not isinstance(contract, dict):
    raise SystemExit("source_behavior_contract.json must be an object")
schema_version = contract.get("schema_version")
warnings = []
if schema_version is None:
    warnings.append("schema_version missing; treating contract as best-effort schema v1")
elif not isinstance(schema_version, (int, float, str)) or (isinstance(schema_version, str) and not schema_version.strip()):
    raise SystemExit("source_behavior_contract.json schema_version must be a non-empty string or number when present")
if not isinstance(contract.get("source_summary"), str) or not contract["source_summary"].strip():
    raise SystemExit("source_behavior_contract.json missing source_summary")

def has_contract_entry_content(value):
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float, bool)):
        return True
    if isinstance(value, list):
        return any(has_contract_entry_content(item) for item in value)
    if isinstance(value, dict):
        return any(has_contract_entry_content(item) for item in value.values())
    return False

def first_present(*keys):
    for key in keys:
        if key in contract:
            return key, contract[key]
    return "", None

def require_content(*keys):
    used_key, value = first_present(*keys)
    if not has_contract_entry_content(value):
        label = " or ".join(keys)
        raise SystemExit(f"source_behavior_contract.json must contain non-empty {label}")
    return used_key, value

def require_non_empty_array(key):
    value = contract.get(key)
    if not isinstance(value, list) or not value or any(not has_contract_entry_content(item) for item in value):
        raise SystemExit(f"source_behavior_contract.json must contain non-empty array {key}")

for key in ["source_entrypoints", "visible_behaviors", "typical_inputs", "safety_boundaries"]:
    require_non_empty_array(key)
require_content("state_and_memory", "state_memory")
require_content("output_contracts", "output_contract")
mapping = contract.get("migration_mapping")
if not isinstance(mapping, dict) or not has_contract_entry_content(mapping):
    raise SystemExit("source_behavior_contract.json missing non-empty migration_mapping object")

required_dimensions = {
    "normal_behavior",
    "tool_or_capability",
    "unsupported_external_or_safety_boundary",
}
coverage_value = contract.get("eval_coverage", [])
if not isinstance(coverage_value, list) or not coverage_value or any(not isinstance(item, str) or not item.strip() for item in coverage_value):
    raise SystemExit("source_behavior_contract.json eval_coverage must be a non-empty string array")
coverage = set(coverage_value)
missing = sorted(required_dimensions - coverage)
if missing:
    raise SystemExit("source_behavior_contract.json eval_coverage missing: " + ", ".join(missing))
print(json.dumps({"source_entrypoints": len(contract["source_entrypoints"]), "visible_behaviors": len(contract["visible_behaviors"]), "eval_coverage": sorted(coverage), "warnings": warnings}, ensure_ascii=False))
PY
  then
    record_check "behavior_contract:schema" "passed" "$(tail -1 "$validation_tmp_dir"/agentkit-migrate-behavior-contract.log)"
  else
    record_check "behavior_contract:schema" "failed" "$(tail -20 "$validation_tmp_dir"/agentkit-migrate-behavior-contract.log | tr '\n' ' ')"
    failed=1
  fi

  if "$python_bin" - <<'PY' >"$validation_tmp_dir"/agentkit-migrate-eval.log 2>&1
import json
from pathlib import Path

cases = json.loads(Path("eval/cases.json").read_text(encoding="utf-8"))
if not isinstance(cases, list) or len(cases) < 3:
    raise SystemExit("eval/cases.json must contain at least 3 cases")
for i, row in enumerate(cases, 1):
    if not isinstance(row, dict):
        raise SystemExit(f"case #{i} must be an object")
    allowed_keys = {"input", "reference_output"}
    extra_keys = sorted(set(row) - allowed_keys)
    if extra_keys:
        raise SystemExit(f"case #{i} has unsupported fields: {', '.join(extra_keys)}; eval/cases.json must only contain input and reference_output")
    for key in ("input", "reference_output"):
        value = row.get(key)
        if not isinstance(value, str) or not value.strip():
            raise SystemExit(f"case #{i} missing non-empty {key}")
rubric = Path("eval/rubric.md").read_text(encoding="utf-8").strip()
if len(rubric) < 80:
    raise SystemExit("eval/rubric.md is too short")
for variable in ("{{input}}", "{{output}}", "{{reference_output}}"):
    if variable not in rubric:
        raise SystemExit(f"eval/rubric.md must reference AgentKit evaluator variable {variable}")
if not any(token in rubric for token in ("0.5", "numeric", "数值", "分数")):
    raise SystemExit("eval/rubric.md must require a parseable numeric score such as 1, 0.5, or 0")
rubric_lower = rubric.lower()
if not ("safety" in rubric_lower or "安全" in rubric):
    raise SystemExit("eval/rubric.md must include a safety-boundary dimension")
if not (
    "honest" in rubric_lower
    or "limitation" in rubric_lower
    or "unsupported" in rubric_lower
    or "限制" in rubric
    or "不支持" in rubric
):
    raise SystemExit("eval/rubric.md must include honest limitation or unsupported-system reporting")
PY
  then
    record_check "eval:suite" "passed" "eval/cases.json and eval/rubric.md are runnable with agentkit eval dataset/evaluator commands"
  else
    record_check "eval:suite" "failed" "$(tail -20 "$validation_tmp_dir"/agentkit-migrate-eval.log | tr '\n' ' ')"
    failed=1
  fi
fi

if [ -n "$record_python" ]; then
  "$record_python" - "$checks_file" "$source_capabilities_file" "$findings_file" "$decision_file" <<'PY'
import json
import pathlib
import sys
from datetime import datetime, timezone

checks_path = pathlib.Path(sys.argv[1])
source_capabilities_path = pathlib.Path(sys.argv[2])
findings_path = pathlib.Path(sys.argv[3])
decision_path = pathlib.Path(sys.argv[4])
checks = [json.loads(line) for line in checks_path.read_text(encoding="utf-8").splitlines() if line.strip()]
metadata_path = pathlib.Path("migration_metadata.json")
try:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
except Exception:
    metadata = {}
try:
    source_capabilities = json.loads(source_capabilities_path.read_text(encoding="utf-8"))
except Exception:
    source_capabilities = {
        "observability": {"detected": False, "default_enable_apmplus": True, "signals": []},
        "guardrails": {"detected": False, "default_enable_llm_shield": False, "signals": []},
    }
try:
    behavior_contract = json.loads(pathlib.Path("source_behavior_contract.json").read_text(encoding="utf-8"))
except Exception:
    behavior_contract = {}

FATAL_CHECKS = {
    "python",
    "compileall",
    "import:assistant.agent.root_agent",
    "import:main.app",
    "requirements:platform",
    "main:agentkit_server_app",
    "cli_contract:project",
    "cli_contract:app_name",
    "cli_contract:model_api_key_env",
    "cli_contract:model_api_key_agent",
    "cli_contract:model_api_key_no_empty_alias",
    "cli_contract:model_api_base_env",
    "cli_contract:model_id",
    "cli_contract:model_base_url",
}
FATAL_REQUIRED_FILES = {
    "file:assistant/__init__.py",
    "file:assistant/agent.py",
    "file:main.py",
    "file:requirements.txt",
    "file:Dockerfile",
    "file:.agentkit/agentkit.yaml",
    "file:.env.example",
}


def classify(check):
    name = str(check.get("name") or "")
    status = str(check.get("status") or "")
    detail = str(check.get("detail") or "")
    if status == "passed":
        severity = "info"
    elif status == "warning":
        severity = "degraded"
    elif name in FATAL_CHECKS or name in FATAL_REQUIRED_FILES:
        severity = "fatal"
    else:
        severity = "repairable"
    return {
        "name": name,
        "status": status,
        "severity": severity,
        "detail": detail,
    }


classified_checks = [classify(check) for check in checks]
findings = {
    "schema_version": 1,
    "status": "failed",
    "summary": {"fatal": 0, "repairable": 0, "degraded": 0, "info": 0},
    "fatal": [],
    "repairable": [],
    "degraded": [],
    "info": [],
}
for check in classified_checks:
    severity = check["severity"]
    findings[severity].append(check)
    findings["summary"][severity] += 1
if findings["summary"]["fatal"] == 0 and findings["summary"]["repairable"] == 0:
    findings["status"] = "passed"
terminal_state = (
    "Failed"
    if findings["summary"]["fatal"] > 0 or findings["summary"]["repairable"] > 0
    else ("SucceedWithWarnings" if findings["summary"]["degraded"] > 0 else "Succeed")
)
findings_path.write_text(json.dumps(findings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
decision_path.write_text(
    json.dumps(
        {
            "status": findings["status"],
            "terminal_state": terminal_state,
            "blocking_count": findings["summary"]["fatal"] + findings["summary"]["repairable"],
            "fatal": findings["summary"]["fatal"],
            "repairable": findings["summary"]["repairable"],
            "degraded": findings["summary"]["degraded"],
        },
        ensure_ascii=False,
    )
    + "\n",
    encoding="utf-8",
)
status = findings["status"]

def has_content(value):
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float, bool)):
        return True
    if isinstance(value, list):
        return any(has_content(item) for item in value)
    if isinstance(value, dict):
        return any(has_content(item) for item in value.values())
    return False

def first_content(record, *keys):
    if not isinstance(record, dict):
        return []
    for key in keys:
        if key in record and has_content(record[key]):
            return record[key]
    return []

def as_list(value):
    if isinstance(value, list):
        return value
    if has_content(value):
        return [value]
    return []

metadata["post_step_validation"] = {
    "status": status,
    "validated_at": datetime.now(timezone.utc).isoformat(),
    "checks": classified_checks,
    "summary": findings["summary"],
    "findings_file": "validation_findings.json",
    "model_smoke": {
        "status": "not_run",
        "reason": "default post-step validation is deterministic; cloud deploy/invoke or explicit model smoke is validated outside this step",
    },
}
try:
    eval_cases = json.loads(pathlib.Path("eval/cases.json").read_text(encoding="utf-8"))
    eval_case_count = len(eval_cases) if isinstance(eval_cases, list) else 0
except Exception:
    eval_case_count = 0
metadata["behavior_contract"] = {
    "status": "ready" if status == "passed" and behavior_contract else "invalid",
    "file": "source_behavior_contract.json",
    "source_summary": behavior_contract.get("source_summary", ""),
    "source_entrypoints": behavior_contract.get("source_entrypoints", []),
    "visible_behaviors": behavior_contract.get("visible_behaviors", []),
    "output_contracts": as_list(first_content(behavior_contract, "output_contracts", "output_contract")),
    "preserved_behaviors": as_list(first_content(behavior_contract.get("migration_mapping", {}), "instruction")) or as_list(behavior_contract.get("migration_mapping", {})),
    "unsupported_or_degraded_behaviors": as_list(first_content(behavior_contract, "unsupported_or_degraded_behaviors", "unsupported_degraded_behaviors")),
    "eval_coverage": behavior_contract.get("eval_coverage", []),
}
metadata["eval_suite"] = {
    "status": "ready" if status == "passed" and eval_case_count >= 3 else "invalid",
    "case_count": eval_case_count,
    "dataset_file": "eval/cases.json",
    "rubric_file": "eval/rubric.md",
    "commands": [
        "agentkit eval dataset create --name <dataset-name> --schema input,reference_output",
        "agentkit eval dataset add <dataset-id> --file eval/cases.json",
        "agentkit eval evaluator create --name <evaluator-name> --from-template <template-with-input-output-reference_output> --prompt-file eval/rubric.md --model <judge-model>",
        "agentkit eval run --dataset <dataset-id> --evaluator <evaluator-id> --target <runtime-name>",
    ],
}
metadata["validation_findings"] = {
    "status": findings["status"],
    "summary": findings["summary"],
    "file": "validation_findings.json",
}
metadata["source_context"] = source_capabilities.get("source_context", {})
metadata["observability"] = {
    "status": "ready",
    "server_trace": "AgentkitAgentServerApp request/session APIs remain available. Top-level apmplus defaults to true for migrated AgentKit runtimes.",
    "agent_trace": "VeADK agent tracing is enabled when ENABLE_APMPLUS=true and APMPlus credentials are available through an explicit optional APMPlus API key env, VOLCENGINE_ACCESS_KEY/VOLCENGINE_SECRET_KEY, or VeFaaS IAM. Endpoint/service-name exporter overrides are omitted when empty.",
    "default_enabled": True,
    "manual_override": "Set ENABLE_APMPLUS=false at deploy/runtime to explicitly disable migrated AgentKit/VeADK APMPlus tracing.",
    "source_detection": source_capabilities.get("observability", {}),
    "optional_envs": [
        "ENABLE_APMPLUS",
        "OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY (optional, omit when empty)",
        "OBSERVABILITY_OPENTELEMETRY_APMPLUS_ENDPOINT (optional, omit when empty)",
        "OBSERVABILITY_OPENTELEMETRY_APMPLUS_SERVICE_NAME (optional, omit when empty)",
    ],
}
agentkit_yaml_text = pathlib.Path(".agentkit/agentkit.yaml").read_text(encoding="utf-8", errors="replace")
llm_shield_credentials_configured = (
    "TOOL_LLM_SHIELD_APP_ID" in agentkit_yaml_text
    and "TOOL_LLM_SHIELD_API_KEY" in agentkit_yaml_text
)
metadata["safety_guardrails"] = {
    "status": "ready",
    "policy": "Generated instructions and tools must preserve source safety boundaries, avoid plaintext secrets, and report unsupported external systems instead of faking success.",
    "runtime": "VeADK LLM Shield callbacks are wired through ENABLE_LLM_SHIELD and require TOOL_LLM_SHIELD_APP_ID plus TOOL_LLM_SHIELD_API_KEY when explicitly enabled; empty credential envs are omitted.",
    "default_enabled": bool(source_capabilities.get("guardrails", {}).get("default_enable_llm_shield")) and llm_shield_credentials_configured,
    "manual_override": "Set ENABLE_LLM_SHIELD=true or false at deploy/runtime to override the source-detected default.",
    "source_detection": source_capabilities.get("guardrails", {}),
    "eval_required": "source_behavior_contract.json eval_coverage plus eval/cases.json and eval/rubric.md must include behavior preservation, safety boundary, and honest limitation checks.",
}
metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

report_path = pathlib.Path("convert_report.md")
report = report_path.read_text(encoding="utf-8") if report_path.exists() else "# Migration Report\n"
for marker in ("\n## Source Behavior Contract\n", "\n## Post-step Validation\n"):
    if marker in report:
        report = report.split(marker, 1)[0].rstrip()
report = report.rstrip()
report += "\n## Source Behavior Contract\n\n"
report += f"- status: {metadata['behavior_contract']['status']}\n"
report += f"- summary: {metadata['behavior_contract']['source_summary']}\n"
report += f"- source_entrypoints: {len(metadata['behavior_contract']['source_entrypoints'])}\n"
report += f"- visible_behaviors: {len(metadata['behavior_contract']['visible_behaviors'])}\n"
report += f"- unsupported_or_degraded_behaviors: {len(metadata['behavior_contract']['unsupported_or_degraded_behaviors'])}\n"
report += f"- eval_coverage: {', '.join(metadata['behavior_contract']['eval_coverage'])}\n"
report += "\n## Post-step Validation\n\n"
report += f"- status: {status}\n"
report += f"- fatal: {findings['summary']['fatal']}\n"
report += f"- repairable: {findings['summary']['repairable']}\n"
report += f"- degraded: {findings['summary']['degraded']}\n"
report += "- findings: `validation_findings.json`\n"
for check in classified_checks:
    report += f"- {check['name']}: {check['status']} / {check['severity']} - {check['detail']}\n"
report += "- model_smoke: not_run - default post-step is deterministic; run cloud deploy/invoke separately when requested.\n"
source_context = source_capabilities.get("source_context", {})
report += "\n## Source Context Evidence\n\n"
report += f"- entrypoints: {len(source_context.get('entrypoints', []) or [])}\n"
report += f"- env_requirements: {len(source_context.get('env_requirements', []) or [])}\n"
report += f"- external_systems: {len(source_context.get('external_systems', []) or [])}\n"
report += "\n## Deploy-time Eval Suite\n\n"
report += f"- status: {metadata['eval_suite']['status']}\n"
report += f"- cases: {metadata['eval_suite']['case_count']} (`eval/cases.json`)\n"
report += "- rubric: `eval/rubric.md`\n"
report += "\n## Observability\n\n"
report += "- server_trace: AgentkitAgentServerApp request/session APIs remain available; top-level `apmplus` defaults to true for migrated AgentKit runtimes.\n"
report += f"- source_detection: detected={bool(source_capabilities.get('observability', {}).get('detected'))}; migrated_default_enable_apmplus=true.\n"
report += "- agent_trace: VeADK APMPlus tracing is enabled when ENABLE_APMPLUS=true and credentials are available via an explicit optional APMPlus API key env, VOLCENGINE_ACCESS_KEY/VOLCENGINE_SECRET_KEY, or VeFaaS IAM; endpoint/service-name exporter overrides are omitted when empty.\n"
report += "- manual_override: set ENABLE_APMPLUS=false to explicitly disable migrated APMPlus tracing.\n"
report += "\n## Safety Guardrails\n\n"
report += "- preserve source safety boundaries in agent instructions and tool adapters.\n"
report += f"- source_detection: detected={bool(source_capabilities.get('guardrails', {}).get('detected'))}, requested_default_enable_llm_shield={bool(source_capabilities.get('guardrails', {}).get('default_enable_llm_shield'))}.\n"
report += "- runtime LLM Shield callbacks are enabled with ENABLE_LLM_SHIELD=true plus TOOL_LLM_SHIELD_APP_ID and TOOL_LLM_SHIELD_API_KEY; empty credential envs are omitted, so default remains false when credentials are unavailable.\n"
report += "- manual_override: set ENABLE_LLM_SHIELD=true or false.\n"
report += "- never write plaintext secrets or fake database/cloud/APM/HTTP/MCP/model success.\n"
report += "- include safety-boundary and honest-limitation dimensions in deploy-time eval.\n"
report_path.write_text(report, encoding="utf-8")
PY
fi

validation_status="failed"
terminal_state="Failed"
blocking_count="$failed"
fatal_count=0
repairable_count=0
degraded_count=0
if [ -n "$record_python" ] && [ -s "$decision_file" ]; then
  validation_status="$("$record_python" - "$decision_file" status <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8")).get(sys.argv[2], "failed"))
PY
)"
  terminal_state="$("$record_python" - "$decision_file" terminal_state <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8")).get(sys.argv[2], "Failed"))
PY
)"
  blocking_count="$("$record_python" - "$decision_file" blocking_count <<'PY'
import json, sys
print(int(json.load(open(sys.argv[1], encoding="utf-8")).get(sys.argv[2], 1)))
PY
)"
  fatal_count="$("$record_python" - "$decision_file" fatal <<'PY'
import json, sys
print(int(json.load(open(sys.argv[1], encoding="utf-8")).get(sys.argv[2], 0)))
PY
)"
  repairable_count="$("$record_python" - "$decision_file" repairable <<'PY'
import json, sys
print(int(json.load(open(sys.argv[1], encoding="utf-8")).get(sys.argv[2], 0)))
PY
)"
  degraded_count="$("$record_python" - "$decision_file" degraded <<'PY'
import json, sys
print(int(json.load(open(sys.argv[1], encoding="utf-8")).get(sys.argv[2], 0)))
PY
)"
fi

if [ "$blocking_count" -eq 0 ]; then
  if [ "$terminal_state" = "SucceedWithWarnings" ]; then
    printf 'Deterministic post-step validation passed with degraded findings: metadata=migration_metadata.json report=convert_report.md findings=validation_findings.json degraded=%s\n' "$degraded_count"
  else
    printf 'Deterministic post-step validation passed: metadata=migration_metadata.json report=convert_report.md eval_cases=eval/cases.json\n'
  fi
else
  printf 'Deterministic post-step validation failed: fatal=%s repairable=%s; see validation_findings.json, migration_metadata.json post_step_validation.checks, and convert_report.md\n' "$fatal_count" "$repairable_count"
fi

[ "$blocking_count" -eq 0 ]
