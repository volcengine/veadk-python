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

"""Cloud side of the tunnel: mount routes onto an existing FastAPI app.

``mount_tunnel(app, ...)`` adds:

- ``WS /tunnel/connect`` — a connector connects (outbound from the enterprise),
  authenticates, and registers its servers to a *named* agent.
- ``/tunnel/mcp/{agent}/{server}[/{path}]`` — an internal proxy the agent's
  ``MCPToolset`` hits over loopback; each request is forwarded over the
  connector's WebSocket to the real local server and the (possibly streaming)
  response is piped back.
- ``GET /tunnel/servers`` — list online servers (for a web UI / health).

Multi-replica caveat: a connector's WebSocket lives on one process, and the
registry is in-process, so the agent run must hit the same process. Use a single
replica or sticky routing until a shared registry/bus is added.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from veadk.tunnel.registry import ServerDescriptor, TunnelRegistry, get_registry
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

_HOP_BY_HOP = {
    "content-length",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "upgrade",
    "host",
}


def _filter_headers(headers: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in _HOP_BY_HOP}


@dataclass
class ConnectorConnection:
    """One connected connector (enterprise side) and the servers it advertises."""

    connector_id: str
    websocket: WebSocket
    agent_name: str
    servers: list[ServerDescriptor]
    pending: dict[str, "asyncio.Queue"] = field(default_factory=dict)

    async def request(self, server: str, payload: dict) -> "asyncio.Queue":
        """Send an http_request frame and return the queue it will stream into."""
        req_id = str(uuid.uuid4())
        queue: asyncio.Queue = asyncio.Queue()
        self.pending[req_id] = queue
        await self.websocket.send_text(
            json.dumps(
                {"type": "http_request", "id": req_id, "server": server, **payload}
            )
        )
        return queue

    def dispatch(self, msg: dict) -> None:
        """Route an inbound frame from the connector to its waiting queue."""
        req_id = msg.get("id")
        queue = self.pending.get(req_id) if req_id else None
        if queue is None:
            return
        t = msg.get("type")
        if t == "http_response":
            queue.put_nowait(("head", msg.get("status", 200), msg.get("headers", {})))
        elif t == "http_chunk":
            queue.put_nowait(("chunk", msg.get("data", "")))
        elif t == "http_end":
            queue.put_nowait(("end", None))
            self.pending.pop(req_id, None)
        elif t == "http_error":
            queue.put_nowait(("error", msg.get("error", "tunnel error")))
            self.pending.pop(req_id, None)

    def fail_all(self) -> None:
        for queue in self.pending.values():
            queue.put_nowait(("error", "connector disconnected"))
        self.pending.clear()


# Default auth: ``token`` must match (if configured) and the target agent must be
# in ``allowed_agents`` (if configured).
AuthFn = Callable[[Optional[str], str], bool]


def mount_tunnel(
    app: FastAPI,
    *,
    token: Optional[str] = None,
    allowed_agents: Optional[list[str]] = None,
    auth: Optional[AuthFn] = None,
    registry: Optional[TunnelRegistry] = None,
) -> None:
    """Mount the tunnel routes onto ``app``.

    Args:
        app: The FastAPI app (e.g. from ADK ``get_fast_api_app``).
        token: Shared tunnel token a connector must present (header
            ``Authorization: Bearer <token>`` or query ``?token=``). ``None``
            disables the token check (not recommended).
        allowed_agents: Agent names allowed to receive registrations (typically
            the ones with ``enable_tunnel=True``). ``None`` allows any.
        auth: Custom ``(presented_token, agent_name) -> bool`` overriding the
            default token/allowed_agents check.
        registry: Registry to use; defaults to the process-global one.
    """
    reg = registry or get_registry()

    def _authorize(presented: Optional[str], agent: str) -> bool:
        if auth is not None:
            return auth(presented, agent)
        if token is not None and presented != token:
            return False
        if allowed_agents is not None and agent not in allowed_agents:
            return False
        return True

    @app.websocket("/tunnel/connect")
    async def tunnel_connect(ws: WebSocket):  # noqa: ANN202
        await ws.accept()
        connector_id = str(uuid.uuid4())[:8]

        # token may come via query (?token=) or Authorization header
        presented = ws.query_params.get("token")
        if not presented:
            authz = ws.headers.get("authorization", "")
            if authz.lower().startswith("bearer "):
                presented = authz[7:]

        try:
            raw = await ws.receive_text()
            register = json.loads(raw)
        except Exception:
            await ws.close(code=4400, reason="expected a register message")
            return

        if register.get("type") != "register":
            await ws.close(code=4400, reason="first message must be `register`")
            return

        agent_name = register.get("agent", "")
        # token in the register body is also accepted (convenience)
        presented = presented or register.get("token")

        if not agent_name or not _authorize(presented, agent_name):
            await ws.send_text(
                json.dumps(
                    {
                        "type": "register_ack",
                        "ok": False,
                        "error": f"not authorized to mount to agent `{agent_name}`",
                    }
                )
            )
            await ws.close(code=4403, reason="unauthorized")
            logger.warning(f"Rejected connector for agent `{agent_name}` (auth failed)")
            return

        servers = [ServerDescriptor(**s) for s in register.get("servers", [])]
        conn = ConnectorConnection(
            connector_id=connector_id,
            websocket=ws,
            agent_name=agent_name,
            servers=servers,
        )
        reg.add_connection(conn)
        await ws.send_text(
            json.dumps(
                {"type": "register_ack", "ok": True, "connector_id": connector_id}
            )
        )

        try:
            while True:
                raw = await ws.receive_text()
                conn.dispatch(json.loads(raw))
        except WebSocketDisconnect:
            pass
        except Exception as e:  # pragma: no cover
            logger.warning(f"Connector {connector_id} ws error: {e}")
        finally:
            conn.fail_all()
            reg.remove_connection(connector_id)

    async def _proxy(agent: str, server: str, request: Request) -> Response:
        conn = reg.find_connection(agent, server)
        if conn is None:
            return Response("tunnel server not connected", status_code=503)

        body = await request.body()
        payload = {
            "method": request.method,
            "headers": _filter_headers(dict(request.headers)),
            "body": body.decode("utf-8", errors="ignore"),
        }
        queue = await conn.request(server, payload)

        head = await queue.get()
        if head[0] == "error":
            return Response(f"tunnel error: {head[1]}", status_code=502)
        _, status, headers = head

        async def gen():
            while True:
                item = await queue.get()
                if item[0] == "chunk":
                    yield item[1].encode("utf-8")
                elif item[0] == "end":
                    break
                elif item[0] == "error":
                    break

        return StreamingResponse(
            gen(),
            status_code=status,
            headers=_filter_headers(headers),
        )

    @app.api_route("/tunnel/mcp/{agent}/{server}", methods=["GET", "POST", "DELETE"])
    async def proxy_root(agent: str, server: str, request: Request):  # noqa: ANN202
        return await _proxy(agent, server, request)

    @app.api_route(
        "/tunnel/mcp/{agent}/{server}/{path:path}",
        methods=["GET", "POST", "DELETE"],
    )
    async def proxy_path(agent: str, server: str, path: str, request: Request):  # noqa: ANN202
        return await _proxy(agent, server, request)

    @app.get("/tunnel/servers")
    async def list_servers(agent: Optional[str] = None) -> dict[str, Any]:  # noqa: ANN202
        if agent:
            servers = reg.list_servers(agent)
        else:
            servers = []  # listing across agents is intentionally not exposed
        return {
            "agent": agent,
            "servers": [s.model_dump(exclude={"headers", "query"}) for s in servers],
        }

    logger.info(
        f"Tunnel routes mounted (token={'set' if token else 'none'}, "
        f"allowed_agents={allowed_agents or 'any'})"
    )


def mount_tunnel_if_enabled(app: FastAPI, agents: list, **kwargs) -> bool:
    """Mount the tunnel only if at least one agent has ``enable_tunnel=True``.

    Args:
        app: The FastAPI app.
        agents: Loaded agent objects to inspect.
        **kwargs: Forwarded to :func:`mount_tunnel` (e.g. ``token=...``).

    Returns:
        ``True`` if the tunnel was mounted, else ``False``.
    """
    enabled = [a.name for a in agents if getattr(a, "enable_tunnel", False)]
    if not enabled:
        return False
    mount_tunnel(app, allowed_agents=enabled, **kwargs)
    return True
