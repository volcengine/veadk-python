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

# in case of uvicorn and fastapi not installed in user's requirements.txt
python3 -m pip install uvicorn[standard]

python3 -m pip install fastapi

USE_STUDIO=${USE_STUDIO:-False}
USE_ADK_WEB=${USE_ADK_WEB:-False}

if [ "$USE_STUDIO" = "True" ]; then
    echo "USE_STUDIO is True, running veadk studio"
    # running veadk studio
    exec python3 -m uvicorn studio_app:app --host $HOST --port $PORT --timeout-graceful-shutdown $TIMEOUT --loop asyncio
elif [ "$USE_STUDIO" = "False" ]; then
    echo "USE_STUDIO is False"

    if [ "$USE_ADK_WEB" = "True" ]; then
        echo "USE_ADK_WEB is True, running veadk web"
        # running veadk web
        cd ../
        exec python3 -m veadk.cli.main web --host "0.0.0.0"
    else
        echo "USE_ADK_WEB is False, running a2a server"
        exec python3 -m uvicorn app:app --host $HOST --port $PORT --timeout-graceful-shutdown $TIMEOUT --loop asyncio
    fi
else
    # running a2a server
    exec python3 -m uvicorn app:app --host $HOST --port $PORT --timeout-graceful-shutdown $TIMEOUT --loop asyncio
fi