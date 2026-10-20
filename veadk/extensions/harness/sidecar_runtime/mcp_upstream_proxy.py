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

"""Loopback ownership boundary for managed Sidecar MCP upstream credentials."""

from __future__ import annotations

import hmac
import json
import re
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
_ROUTE_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?")


class ManagedMcpUpstreamRelay:
    """Expose one authenticated loopback route for one MCP upstream.

    The private Sidecar sees only a short-lived internal credential. The relay
    removes it and applies the optional per-upstream authorization selected in
    Studio, so unauthenticated and differently authenticated MCP servers share
    the legacy Sidecar runtime safely.
    """

    def __init__(
        self,
        upstream_url: str,
        *,
        route: str,
        upstream_authorization: str | None,
        internal_api_key: str,
    ) -> None:
        self._upstream = _validated_upstream_url(upstream_url)
        self._route = _validated_route(route)
        self._authorization = _validated_authorization(upstream_authorization)
        self._internal_authorization = f"Bearer {str(internal_api_key).strip()}"
        if self._internal_authorization == "Bearer ":
            raise ValueError("managed MCP relay internal API key is required")
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="veadk-managed-mcp-upstream",
            daemon=True,
        )
        self._thread.start()

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/{self._route}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=5)

    def _target_url(self, request_path: str) -> str:
        incoming = urllib.parse.urlsplit(request_path)
        source_path = f"/{self._route}"
        if incoming.path == source_path:
            suffix = ""
        elif incoming.path.startswith(source_path + "/"):
            suffix = incoming.path[len(source_path) :]
        else:
            suffix = incoming.path
        target = urllib.parse.urlsplit(self._upstream)
        target_path = target.path.rstrip("/") + suffix
        query = "&".join(value for value in (target.query, incoming.query) if value)
        return urllib.parse.urlunsplit(
            (target.scheme, target.netloc, target_path or "/", query, "")
        )

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        relay = self

        class RelayHandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: object) -> None:
                del format, args
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
                incoming_authorization = self.headers.get("Authorization", "")
                if not hmac.compare_digest(
                    incoming_authorization, relay._internal_authorization
                ):
                    self.send_response(401)
                    self.send_header("Content-Length", "0")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.close_connection = True
                    return

                content_length = int(self.headers.get("Content-Length", "0") or 0)
                body = self.rfile.read(content_length) if content_length else None
                headers = {
                    name: value
                    for name, value in self.headers.items()
                    if name.lower() not in _HOP_BY_HOP_HEADERS
                    and name.lower() not in {"authorization", "content-length", "host"}
                }
                if relay._authorization:
                    headers["Authorization"] = relay._authorization
                request = urllib.request.Request(
                    relay._target_url(self.path),
                    data=body,
                    headers=headers,
                    method=self.command,
                )
                try:
                    response = relay._opener.open(request, timeout=60)
                except urllib.error.HTTPError as error:
                    response = error
                except (OSError, urllib.error.URLError):
                    self._send_unavailable()
                    return

                with response:
                    status = response.getcode()
                    if not isinstance(status, int):
                        self._send_unavailable()
                        return
                    self.send_response(status)
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

            def _send_unavailable(self) -> None:
                payload = json.dumps(
                    {"status": "error", "error": "managed_mcp_upstream_unavailable"}
                ).encode("utf-8")
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Connection", "close")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(payload)
                self.close_connection = True

        return RelayHandler


def _validated_upstream_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(str(value).strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("managed MCP upstream must be an HTTP(S) URL")
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), parsed.query, "")
    )


def _validated_route(value: str) -> str:
    route = str(value).strip().lower()
    if _ROUTE_RE.fullmatch(route) is None:
        raise ValueError("managed MCP relay route is invalid")
    return route


def _validated_authorization(value: str | None) -> str:
    authorization = str(value or "").strip()
    if not authorization:
        return ""
    if (
        not authorization.startswith("Bearer ")
        or not authorization[7:]
        or "\r" in authorization
        or "\n" in authorization
    ):
        raise ValueError("managed MCP upstream authorization is invalid")
    return authorization


__all__ = ["ManagedMcpUpstreamRelay"]
