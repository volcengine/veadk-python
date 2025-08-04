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

# running
exec python3 -m uvicorn app:app --host $HOST --port $PORT --timeout-graceful-shutdown $TIMEOUT
