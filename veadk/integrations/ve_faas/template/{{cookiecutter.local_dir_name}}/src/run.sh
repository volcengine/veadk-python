#!/bin/bash
set -ex
cd `dirname $0`

# A special check for CLI users (run.sh should be located at the 'root' dir)
if [ -d "output" ]; then
    cd ./output/
fi

# Default values for host and port
HOST="0.0.0.0"
PORT=${_FAAS_RUNTIME_PORT:-8000}
TIMEOUT=${_FAAS_FUNC_TIMEOUT}

export SERVER_HOST=$HOST
export SERVER_PORT=$PORT

export PYTHONPATH=$PYTHONPATH:./site-packages
# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --port)
            PORT="$2"
            shift 2
            ;;
        --host)
            HOST="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

# in case of deployment deps not installed in user's requirements.txt
if pip list | grep -q "^fastapi \|^uvicorn "; then
    echo "fastapi and uvicorn already installed"
else
    python3 -m pip install uvicorn[standard] fastapi
fi

# Check if MODEL_AGENT_API_KEY is set
if [ -z "$MODEL_AGENT_API_KEY" ]; then
    echo "MODEL_AGENT_API_KEY is not set. Please set it in your environment variables."
    exit 1
fi

USE_ADK_WEB=${USE_ADK_WEB:-False}

export SHORT_TERM_MEMORY_BACKEND= # can be `mysql`
export LONG_TERM_MEMORY_BACKEND= # can be `opensearch`

if [ "$USE_ADK_WEB" = "True" ]; then
    echo "USE_ADK_WEB is True, running veadk web"
    exec python3 -m veadk.cli.cli web --host $HOST
else
    echo "USE_ADK_WEB is False, running A2A and MCP server"
    exec python3 -m uvicorn app:app --host $HOST --port $PORT --timeout-graceful-shutdown $TIMEOUT --loop asyncio
fi
