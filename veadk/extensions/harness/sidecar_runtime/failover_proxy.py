# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Stable localhost HTTP relay for Sidecar-to-direct-path failover."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class StableHttpRelay:
    """Expose one stable URL and atomically switch its upstream target."""

    def __init__(self, active_url: str, fallback_url: str) -> None:
        self._active = _validated_base_url(active_url)
        self._fallback = _validated_base_url(fallback_url)
        self._source_path = urllib.parse.urlsplit(self._active).path.rstrip("/")
        self._target = self._active
        self._target_lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="agentkit-harness-direct-failover",
            daemon=True,
        )
        self._thread.start()

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}{self._source_path}"

    def activate_fallback(self) -> None:
        with self._target_lock:
            self._target = self._fallback

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=5)

    def _target_url(self, request_path: str) -> str:
        incoming = urllib.parse.urlsplit(request_path)
        request_base = self._source_path
        if incoming.path == request_base:
            suffix = ""
        elif request_base and incoming.path.startswith(f"{request_base}/"):
            suffix = incoming.path[len(request_base) :]
        else:
            suffix = incoming.path
        with self._target_lock:
            target = urllib.parse.urlsplit(self._target)
        target_path = target.path.rstrip("/") + suffix
        query = "&".join(value for value in (target.query, incoming.query) if value)
        return urllib.parse.urlunsplit(
            (target.scheme, target.netloc, target_path or "/", query, "")
        )

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        relay = self

        class RelayHandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args: object) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802
                self._forward()

            def do_POST(self) -> None:  # noqa: N802
                self._forward()

            def do_PUT(self) -> None:  # noqa: N802
                self._forward()

            def do_PATCH(self) -> None:  # noqa: N802
                self._forward()

            def do_DELETE(self) -> None:  # noqa: N802
                self._forward()

            def do_OPTIONS(self) -> None:  # noqa: N802
                self._forward()

            def do_HEAD(self) -> None:  # noqa: N802
                self._forward()

            def _forward(self) -> None:
                content_length = int(self.headers.get("Content-Length", "0") or 0)
                body = self.rfile.read(content_length) if content_length else None
                headers = {
                    name: value
                    for name, value in self.headers.items()
                    if name.lower() not in _HOP_BY_HOP_HEADERS
                    and name.lower() not in {"host", "content-length"}
                }
                request = urllib.request.Request(
                    relay._target_url(self.path),
                    data=body,
                    headers=headers,
                    method=self.command,
                )
                try:
                    response = urllib.request.urlopen(request, timeout=60)
                except urllib.error.HTTPError as error:
                    response = error
                except (OSError, urllib.error.URLError):
                    payload = json.dumps(
                        {"status": "error", "error": "direct_upstream_unavailable"}
                    ).encode("utf-8")
                    self.send_response(502)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(payload)
                    self.close_connection = True
                    return

                with response:
                    self.send_response(response.getcode())
                    for name, value in response.headers.items():
                        if name.lower() not in _HOP_BY_HOP_HEADERS:
                            self.send_header(name, value)
                    self.send_header("Connection", "close")
                    self.end_headers()
                    if self.command != "HEAD":
                        while chunk := response.read(64 * 1024):
                            self.wfile.write(chunk)
                            self.wfile.flush()
                self.close_connection = True

        return RelayHandler


def _validated_base_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(str(value).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("failover upstream must be an HTTP(S) URL")
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), parsed.query, "")
    )


__all__ = ["StableHttpRelay"]
