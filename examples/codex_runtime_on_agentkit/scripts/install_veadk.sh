#!/bin/sh
# Install veadk-python (with the codex runtime) plus the OpenAI Codex SDK.
#
# The codex runtime lives in veadk on `main`. `openai-codex` is NOT a veadk
# dependency, so it must be installed explicitly here. `openai-codex` pulls in
# `openai-codex-cli-bin`, which ships the Codex CLI binary as a manylinux
# wheel, so there is no separate binary install in the Linux build.
#
# Why a build script instead of a plain `pip install git+...`:
#   A full clone of the veadk repo (large docs/ image history) repeatedly fails
#   mid-fetch on the build network. Here we make the fetch small and robust:
#     - --depth 1            : only the tip commit, no history
#     - --filter=blob:none   : download blobs lazily
#     - --sparse + set veadk : fetch only the veadk/ package (+ root pyproject),
#                              skipping docs/ images entirely
#     - HTTP/1.1             : avoids the HTTP/2 stream error seen otherwise
set -e

BRANCH="main"
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
uv pip install "." openai-codex
