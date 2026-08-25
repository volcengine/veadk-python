# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

"""Stable proxy-free boundary for a managed Sidecar MCP loopback endpoint."""

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
_SESSION_HEADERS = (
    "mcp-session-id",
    "x-session-id",
    "x-harness-session-id",
)
_CANONICAL_SESSION_HEADERS = {
    "mcp-session-id": "Mcp-Session-Id",
    "x-session-id": "X-Session-Id",
    "x-harness-session-id": "X-Harness-Session-Id",
}


class SidecarMcpHttpRelay:
    """Normalize legacy Sidecar MCP framing and session-header dialects."""

    def __init__(self, upstream_url: str, *, timeout_seconds: float) -> None:
        self._upstream = _validated_loopback_url(upstream_url)
        if timeout_seconds <= 0:
            raise ValueError("Sidecar MCP relay timeout must be positive")
        self._timeout_seconds = float(timeout_seconds)
        self._session_dialects: dict[str, str] = {}
        self._session_lock = threading.RLock()
        # The target is always validated loopback. An inherited HTTP_PROXY must
        # never intercept the in-container Agent -> Sidecar hop.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="agentkit-harness-sidecar-mcp-relay",
            daemon=True,
        )
        self._thread.start()

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        upstream = urllib.parse.urlsplit(self._upstream)
        return urllib.parse.urlunsplit(
            ("http", f"{host}:{port}", upstream.path or "/", upstream.query, "")
        )

    def activate_fallback(self) -> None:
        """The managed route intentionally remains fail closed after exit."""

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=5)

    def _remember_session_dialect(self, session_id: str, header: str) -> None:
        with self._session_lock:
            if len(self._session_dialects) >= 1024:
                self._session_dialects.pop(next(iter(self._session_dialects)))
            self._session_dialects[session_id] = header

    def _session_dialect(self, session_id: str) -> str:
        with self._session_lock:
            return self._session_dialects.get(session_id, "mcp-session-id")

    def _forget_session(self, session_id: str) -> None:
        with self._session_lock:
            self._session_dialects.pop(session_id, None)

    def _target_url(self, request_path: str) -> str:
        incoming = urllib.parse.urlsplit(request_path)
        upstream = urllib.parse.urlsplit(self._upstream)
        return urllib.parse.urlunsplit(
            (
                upstream.scheme,
                upstream.netloc,
                incoming.path or upstream.path or "/",
                incoming.query or upstream.query,
                "",
            )
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

            def do_DELETE(self) -> None:  # noqa: N802
                self._forward()

            def do_OPTIONS(self) -> None:  # noqa: N802
                self._forward()

            def do_HEAD(self) -> None:  # noqa: N802
                self._forward()

            def _forward(self) -> None:
                content_length = int(self.headers.get("Content-Length", "0") or 0)
                body = self.rfile.read(content_length) if content_length else None
                session_id = next(
                    (
                        str(value).strip()
                        for name, value in self.headers.items()
                        if str(name).lower() in _SESSION_HEADERS and str(value).strip()
                    ),
                    "",
                )
                headers = {
                    str(name): str(value)
                    for name, value in self.headers.items()
                    if str(name).lower()
                    not in _HOP_BY_HOP_HEADERS
                    | set(_SESSION_HEADERS)
                    | {"content-length", "host"}
                }
                if session_id:
                    dialect = relay._session_dialect(session_id)
                    headers[_CANONICAL_SESSION_HEADERS[dialect]] = session_id
                request = urllib.request.Request(
                    relay._target_url(self.path),
                    data=body,
                    headers=headers,
                    method=self.command,
                )
                try:
                    response = relay._opener.open(
                        request,
                        timeout=relay._timeout_seconds,
                    )
                except urllib.error.HTTPError as error:
                    response = error
                except (OSError, urllib.error.URLError):
                    self._send_unavailable()
                    return

                with response:
                    payload = response.read()
                    response_session_id = ""
                    response_session_header = ""
                    for name, value in response.headers.items():
                        lowered = str(name).lower()
                        if lowered in _SESSION_HEADERS and str(value).strip():
                            response_session_id = str(value).strip()
                            response_session_header = lowered
                            break
                    if response_session_id:
                        relay._remember_session_dialect(
                            response_session_id,
                            response_session_header,
                        )
                    self.send_response(response.getcode())
                    for name, value in response.headers.items():
                        lowered = str(name).lower()
                        if lowered not in (
                            _HOP_BY_HOP_HEADERS
                            | set(_SESSION_HEADERS)
                            | {"content-length"}
                        ):
                            self.send_header(name, value)
                    if response_session_id:
                        self.send_header("Mcp-Session-Id", response_session_id)
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    if self.command != "HEAD" and payload:
                        self.wfile.write(payload)
                if self.command == "DELETE" and session_id:
                    relay._forget_session(session_id)
                self.close_connection = True

            def _send_unavailable(self) -> None:
                payload = json.dumps(
                    {"status": "error", "error": "sidecar_mcp_unavailable"},
                    separators=(",", ":"),
                ).encode()
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Connection", "close")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(payload)
                self.close_connection = True

        return RelayHandler


def _validated_loopback_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(str(value).strip())
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("Sidecar MCP relay upstream must be a loopback HTTP URL")
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, "")
    )


__all__ = ["SidecarMcpHttpRelay"]
