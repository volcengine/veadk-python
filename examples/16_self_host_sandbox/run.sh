#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Ensure veadk and example root are in PYTHONPATH
export PYTHONPATH="$REPO_ROOT:$SCRIPT_DIR:${PYTHONPATH:-}"

# Load .env if present
if [ -f "$SCRIPT_DIR/.env" ]; then
    # Treat .env as defaults. Explicit caller-provided values are useful for
    # testing another Runtime without rewriting a credential file on disk.
    declare -A EXPLICIT_ENV=()
    for key in \
        ANTHROPIC_BASE_URL ANTHROPIC_ENVIRONMENT_ID ANTHROPIC_ENVIRONMENT_KEY \
        SANDBOX_AGENT_ID X_TOP_ACCOUNT_ID SANDBOX_TIMEOUT_SECONDS PORT; do
        if [[ -v $key ]]; then
            EXPLICIT_ENV[$key]="${!key}"
        fi
    done
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
    for key in "${!EXPLICIT_ENV[@]}"; do
        printf -v "$key" '%s' "${EXPLICIT_ENV[$key]}"
        export "$key"
    done
else
    echo "⚠️  未检测到 $SCRIPT_DIR/.env 配置文件。"
    if [ -f "$SCRIPT_DIR/.env.example" ]; then
        echo "💡 提示：请先执行 'cp $SCRIPT_DIR/.env.example $SCRIPT_DIR/.env' 并配置相应密钥。"
    fi
fi

PORT="${PORT:-8067}"

# Check if web mode is requested
if [ "${1:-}" = "--web" ]; then
    shift
    PORT_ARGS=()
    CORS_ARGS=()
    if [[ ! " $* " =~ " --port " ]]; then
        PORT_ARGS=(--port "$PORT")
    fi
    if [[ ! " $* " =~ " --allow_origins " ]] && [ -n "${ALLOW_ORIGINS:-}" ]; then
        IFS=',' read -r -a CONFIGURED_ORIGINS <<< "$ALLOW_ORIGINS"
        for origin in "${CONFIGURED_ORIGINS[@]}"; do
            CORS_ARGS+=(--allow_origins "$origin")
        done
    fi
    echo "🌐 正在启动 VeADK Web 调试界面 (端口: ${PORT})..."
    # Switch into agents directory so veadk web detects self_host_sandbox_agent
    cd "$SCRIPT_DIR/agents"
    if [ -x "$REPO_ROOT/.venv/bin/veadk" ]; then
        exec "$REPO_ROOT/.venv/bin/veadk" web "${PORT_ARGS[@]}" "${CORS_ARGS[@]}" "$@"
    elif command -v uv >/dev/null 2>&1; then
        exec uv run --directory "$REPO_ROOT" --extra sandbox veadk web "${PORT_ARGS[@]}" "${CORS_ARGS[@]}" "$@"
    elif command -v veadk >/dev/null 2>&1; then
        exec veadk web "${PORT_ARGS[@]}" "${CORS_ARGS[@]}" "$@"
    else
        exec python3 -m veadk.cli.cli web "${PORT_ARGS[@]}" "${CORS_ARGS[@]}" "$@"
    fi
fi

cd "$SCRIPT_DIR"

# Prioritize local repo virtualenv if present, otherwise invoke via uv or system python
if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
    exec "$REPO_ROOT/.venv/bin/python" "$SCRIPT_DIR/main.py" "$@"
elif command -v uv >/dev/null 2>&1; then
    exec uv run --directory "$REPO_ROOT" --extra sandbox python "$SCRIPT_DIR/main.py" "$@"
else
    exec python3 "$SCRIPT_DIR/main.py" "$@"
fi
