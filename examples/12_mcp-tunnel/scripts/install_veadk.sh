#!/bin/sh
# Install veadk-python from the feat/tunnel branch (which carries veadk/tunnel),
# plus the WebSocket-capable server deps. Shallow + sparse clone keeps the fetch
# small and reliable (see examples/basic-app for the rationale).
set -e

BRANCH="feat/tunnel"
REPO="https://github.com/volcengine/veadk-python.git"
SRC="/tmp/veadk-src"

git config --global http.version HTTP/1.1
git config --global http.postBuffer 524288000

n=0
until [ "$n" -ge 3 ]; do
    rm -rf "$SRC"
    if git clone --depth 1 --filter=blob:none --sparse --branch "$BRANCH" "$REPO" "$SRC"; then
        break
    fi
    n=$((n + 1))
    echo "git clone failed, retry $n/3..."
    sleep 5
done

cd "$SRC"
git sparse-checkout set veadk
# uvicorn[standard]/websockets are required for the /tunnel/connect WebSocket.
uv pip install "." "uvicorn[standard]" "websockets"
