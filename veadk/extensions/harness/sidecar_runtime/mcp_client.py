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

"""MCP HTTP compatibility used only by managed Harness Sidecar toolsets."""

from __future__ import annotations

import httpx


_MCP_SESSION_HEADER = "mcp-session-id"
_RUNTIME_GATEWAY_SESSION_HEADERS = (
    "x-session-id",
    "x-harness-session-id",
)
_MCP_DEFAULT_TIMEOUT_SECONDS = 30.0
_MCP_DEFAULT_SSE_READ_TIMEOUT_SECONDS = 300.0


async def _normalize_runtime_gateway_session_header(
    response: httpx.Response,
) -> None:
    """Expose a Runtime Gateway session alias under the MCP standard name."""

    if response.headers.get(_MCP_SESSION_HEADER):
        return
    for header in _RUNTIME_GATEWAY_SESSION_HEADERS:
        value = response.headers.get(header)
        if value:
            response.headers[_MCP_SESSION_HEADER] = value
            return


def managed_mcp_http_client_factory(
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | None = None,
    auth: httpx.Auth | None = None,
) -> httpx.AsyncClient:
    """Create an MCP client that accepts Runtime Gateway session aliases.

    Runtime Gateway may expose the upstream ``Mcp-Session-Id`` response as an
    ``X-*`` header. The Python MCP transport only recognizes the standard
    header and otherwise sends follow-up requests without a session. Normalize
    the response at the managed Sidecar boundary while leaving ordinary MCP
    clients unchanged.
    """

    client = httpx.AsyncClient(
        headers=headers,
        timeout=(
            timeout
            if timeout is not None
            else httpx.Timeout(
                _MCP_DEFAULT_TIMEOUT_SECONDS,
                read=_MCP_DEFAULT_SSE_READ_TIMEOUT_SECONDS,
            )
        ),
        auth=auth,
        follow_redirects=True,
        # The generated managed client talks only to the in-process relay.
        # Do not let container HTTP_PROXY/HTTPS_PROXY capture loopback MCP
        # traffic when NO_PROXY is absent or incomplete.
        trust_env=False,
    )
    client.event_hooks["response"].append(_normalize_runtime_gateway_session_header)
    return client


__all__ = ["managed_mcp_http_client_factory"]
