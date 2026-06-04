#!/bin/sh
# Install veadk-python (with the a2ui extra) from the feat/a2ui branch.
#
# Why a build script instead of a plain `pip install git+...`:
#   The veadk repo carries a large docs/ image history, and a full git clone of
#   it from the build network repeatedly failed mid-fetch
#   ("curl 92 HTTP/2 stream not closed cleanly"). Here we make the fetch small
#   and robust:
#     - --depth 1            : only the tip commit, no history
#     - --filter=blob:none   : download blobs lazily
#     - --sparse + set veadk : fetch only the veadk/ package (incl. veadk/webui),
#                              skipping docs/ images entirely
#     - HTTP/1.1             : avoids the HTTP/2 stream error seen above
#   This pulls a few MB instead of the whole repo, so it is fast and reliable.
set -e

BRANCH="feat/a2ui"
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
uv pip install ".[a2ui,pdf]"
