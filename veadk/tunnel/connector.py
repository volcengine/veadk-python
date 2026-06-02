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

"""Enterprise side of the tunnel.

Runs inside the enterprise network, makes an *outbound* WebSocket connection to
the cloud agent, registers one or more local MCP servers to a named agent, and
bridges each forwarded request to the real local server (attaching the
user-provided auth headers / query params). Secrets stay enterprise-side.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Optional

import httpx
import websockets

from veadk.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class LocalServer:
    """A local server to expose through the tunnel.

    Attributes:
        name: Name the cloud agent will see.
        address: Streamable-HTTP MCP endpoint URL of the local server.
        protocol: Resource protocol (``"mcp"`` for now).
        tool_filter: Optional allowlist of tool names.
        headers: Auth headers attached when calling the local server.
        query: Querystring params appended when calling the local server.
    """

    name: str
    address: str
    protocol: str = "mcp"
    tool_filter: Optional[list[str]] = None
    headers: dict[str, str] = field(default_factory=dict)
    query: dict[str, str] = field(default_factory=dict)

    def descriptor(self) -> dict:
        # Note: address/headers/query stay connector-side; we still send name +
        # protocol + tool_filter so the cloud agent can mount it.
        return {
            "name": self.name,
            "protocol": self.protocol,
            "tool_filter": self.tool_filter,
        }


_HOP_BY_HOP = {
    "content-length",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "host",
}


class TunnelConnector:
    """Connects local MCP servers to a cloud agent over an outbound tunnel."""

    def __init__(
        self,
        cloud_url: str,
        agent: str,
        servers: list[LocalServer],
        token: Optional[str] = None,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> None:
        """
        Args:
            cloud_url: Base URL of the cloud agent service, e.g.
                ``https://xxx.apigateway-cn-beijing.volceapi.com``.
            agent: Target agent name (must have ``enable_tunnel=True``).
            servers: Local servers to expose.
            token: Tunnel token issued for that agent (sent via ``?token=``).
            extra_headers: Extra headers for the WebSocket handshake, e.g. the
                edge / API-gateway credential
                (``{"Authorization": "Bearer <key>"}``), kept separate from the
                tunnel ``token``.
        """
        self.cloud_url = cloud_url.rstrip("/")
        self.agent = agent
        self.servers = {s.name: s for s in servers}
        self.token = token
        self.extra_headers = extra_headers or {}
        self._tasks: set = set()

    def _ws_url(self) -> str:
        ws = self.cloud_url.replace("https://", "wss://").replace("http://", "ws://")
        url = f"{ws}/tunnel/connect"
        if self.token:
            url += f"?token={self.token}"
        return url

    async def start(self) -> None:
        ws_url = self._ws_url()
        # Tunnel token goes via ?token=; the Authorization header is free for the
        # edge/API gateway's own credential (passed via extra_headers).
        headers = dict(self.extra_headers)
        async with httpx.AsyncClient() as http:
            async with websockets.connect(ws_url, additional_headers=headers) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "type": "register",
                            "token": self.token,
                            "agent": self.agent,
                            "servers": [s.descriptor() for s in self.servers.values()],
                        }
                    )
                )
                ack = json.loads(await ws.recv())
                if not ack.get("ok"):
                    raise RuntimeError(f"tunnel register rejected: {ack.get('error')}")
                logger.info(
                    f"Tunnel connected: agent=`{self.agent}` "
                    f"servers={list(self.servers)} (connector {ack.get('connector_id')})"
                )

                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("type") == "http_request":
                        # Handle concurrently: a long-lived stream (e.g. the MCP
                        # server->client SSE channel) must not block other
                        # requests like tools/list.
                        task = asyncio.create_task(self._handle_request(ws, http, msg))
                        self._tasks.add(task)
                        task.add_done_callback(self._tasks.discard)

    async def _handle_request(self, ws, http: httpx.AsyncClient, msg: dict) -> None:
        req_id = msg["id"]
        server = self.servers.get(msg.get("server", ""))
        if server is None:
            await ws.send(
                json.dumps(
                    {"type": "http_error", "id": req_id, "error": "unknown server"}
                )
            )
            return

        # Merge forwarded headers with the user-provided auth headers (auth wins).
        fwd = {
            k: v
            for k, v in (msg.get("headers") or {}).items()
            if k.lower() not in _HOP_BY_HOP
        }
        fwd.update(server.headers)

        try:
            async with http.stream(
                method=msg.get("method", "POST"),
                url=server.address,
                headers=fwd,
                params=server.query or None,
                content=msg.get("body", "").encode("utf-8"),
            ) as resp:
                await ws.send(
                    json.dumps(
                        {
                            "type": "http_response",
                            "id": req_id,
                            "status": resp.status_code,
                            "headers": dict(resp.headers),
                        }
                    )
                )
                async for chunk in resp.aiter_bytes():
                    if chunk:
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "http_chunk",
                                    "id": req_id,
                                    "data": chunk.decode("utf-8", errors="ignore"),
                                }
                            )
                        )
                await ws.send(json.dumps({"type": "http_end", "id": req_id}))
        except Exception as e:
            logger.warning(f"Local request to `{server.name}` failed: {e}")
            await ws.send(
                json.dumps({"type": "http_error", "id": req_id, "error": str(e)})
            )
