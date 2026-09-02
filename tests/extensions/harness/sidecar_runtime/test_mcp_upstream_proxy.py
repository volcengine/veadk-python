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

from __future__ import annotations

import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from veadk.extensions.harness.sidecar_runtime.mcp_upstream_proxy import (
    ManagedMcpUpstreamRelay,
)


@pytest.mark.parametrize(
    ("configured_authorization", "expected_authorization"),
    [(None, ""), ("Bearer upstream-test-token", "Bearer upstream-test-token")],
)
def test_managed_mcp_upstream_relay_owns_authorization(
    configured_authorization: str | None,
    expected_authorization: str,
) -> None:
    observed: dict[str, str] = {}

    class UpstreamHandler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            return

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length:
                self.rfile.read(length)
            observed["authorization"] = self.headers.get("Authorization", "")
            observed["path"] = self.path
            payload = b'{"jsonrpc":"2.0","id":1,"result":{"tools":[]}}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    host, port = upstream.server_address[:2]
    relay = ManagedMcpUpstreamRelay(
        f"http://{host}:{port}/upstream/mcp?tenant=test",
        route="mcp-orders-1",
        upstream_authorization=configured_authorization,
        internal_api_key="internal-test-marker",
    )
    try:
        request = urllib.request.Request(
            relay.url + "?trace=1",
            data=b"{}",
            headers={"Authorization": "Bearer internal-test-marker"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 200
        assert observed == {
            "authorization": expected_authorization,
            "path": "/upstream/mcp?tenant=test&trace=1",
        }

        unauthorized = urllib.request.Request(
            relay.url,
            data=b"{}",
            headers={"Authorization": "Bearer wrong-marker"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(unauthorized, timeout=5)
        assert error.value.code == 401
    finally:
        relay.close()
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=5)
