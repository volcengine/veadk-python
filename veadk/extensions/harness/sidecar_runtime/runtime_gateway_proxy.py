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

"""Local transport relay that forces Sidecar traffic through Runtime Gateway."""

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


class RuntimeGatewayHttpRelay:
    """Expose a localhost URL while sending every request through APIG."""

    def __init__(
        self,
        gateway_url: str,
        *,
        source_path: str,
        api_key: str,
        target_port: int,
        timeout_seconds: float,
    ) -> None:
        self._gateway = _validated_gateway_url(gateway_url)
        self._source_path = _normalized_path(source_path)
        self._api_key = str(api_key).strip()
        if not self._api_key:
            raise ValueError("Runtime Gateway API key is required")
        if not 1 <= int(target_port) <= 65535:
            raise ValueError("Runtime Gateway target port is invalid")
        if timeout_seconds <= 0:
            raise ValueError("Runtime Gateway timeout must be positive")
        self._target_port = int(target_port)
        self._timeout_seconds = float(timeout_seconds)
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="agentkit-harness-runtime-gateway",
            daemon=True,
        )
        self._thread.start()

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}{self._source_path}"

    def activate_fallback(self) -> None:
        """Keep the APIG route fail-closed; no direct Sidecar fallback exists."""

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=5)

    def _target_url(self, request_path: str) -> str:
        incoming = urllib.parse.urlsplit(request_path)
        gateway = urllib.parse.urlsplit(self._gateway)
        path = "/".join(
            part.strip("/") for part in (gateway.path, incoming.path) if part.strip("/")
        )
        return urllib.parse.urlunsplit(
            (
                gateway.scheme,
                gateway.netloc,
                f"/{path}" if path else "/",
                incoming.query,
                "",
            )
        )

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        relay = self

        class RelayHandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args: object) -> None:
                return

            def do_GET(self) -> None:
                self._forward()

            def do_POST(self) -> None:
                self._forward()

            def do_PUT(self) -> None:
                self._forward()

            def do_PATCH(self) -> None:
                self._forward()

            def do_DELETE(self) -> None:
                self._forward()

            def do_OPTIONS(self) -> None:
                self._forward()

            def do_HEAD(self) -> None:
                self._forward()

            def _forward(self) -> None:
                content_length = int(self.headers.get("Content-Length", "0") or 0)
                body = self.rfile.read(content_length) if content_length else None
                headers = {
                    str(name): str(value)
                    for name, value in self.headers.items()
                    if str(name).lower() not in _HOP_BY_HOP_HEADERS
                    and str(name).lower()
                    not in {
                        "authorization",
                        "content-length",
                        "host",
                        "x-faas-proxy-port",
                    }
                }
                headers["Authorization"] = f"Bearer {relay._api_key}"
                headers["X-Faas-Proxy-Port"] = str(relay._target_port)
                request = urllib.request.Request(
                    relay._target_url(self.path),
                    data=body,
                    headers=headers,
                    method=self.command,
                )
                try:
                    response = urllib.request.urlopen(
                        request, timeout=relay._timeout_seconds
                    )
                except urllib.error.HTTPError as error:
                    response = error
                except (OSError, urllib.error.URLError):
                    payload = json.dumps(
                        {"status": "error", "error": "runtime_gateway_unavailable"},
                        separators=(",", ":"),
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


def _validated_gateway_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(str(value).strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Runtime Gateway endpoint must be a credential-free HTTP(S) URL"
        )
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "")
    )


def _normalized_path(value: str) -> str:
    parsed = urllib.parse.urlsplit(str(value).strip())
    path = parsed.path.rstrip("/")
    return path if path.startswith("/") else f"/{path}"


__all__ = ["RuntimeGatewayHttpRelay"]
