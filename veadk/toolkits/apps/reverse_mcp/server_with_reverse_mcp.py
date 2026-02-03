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

import asyncio
import json
import uuid
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, Response, WebSocket
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from pydantic import BaseModel

from veadk import Runner
from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from veadk import Agent

logger = get_logger(__name__)

REVERSE_MCP_HEADER_KEY = "X-Reverse-MCP-ID"


class WebsocketSessionManager:
    def __init__(self):
        # ws id -> ws instance
        self.connections: dict[str, WebSocket] = {}

        # ws id -> msg id -> ret
        self.pendings: dict[str, dict[str, asyncio.Future]] = {}

    async def call_mcp_http(self, ws_id: str, request: dict):
        """Forward MCP request to client."""
        try:
            ws = self.connections[ws_id]
        except KeyError:
            logger.error(f"Websocket {ws_id} not found")
            return b""

        msg = {}

        msg["id"] = str(uuid.uuid4())
        msg["type"] = "http_request"
        msg["payload"] = request

        fut = asyncio.get_event_loop().create_future()

        if ws_id not in self.pendings:
            self.pendings[ws_id] = {}

        self.pendings[ws_id][msg["id"]] = fut

        await ws.send_text(json.dumps(msg))
        return await fut

    async def handle_ws_message(self, ws_id: str, raw: str):
        msg = json.loads(raw)
        if msg.get("type") != "http_response":
            return

        req_id = msg["id"]
        fut = self.pendings[ws_id].pop(req_id, None)
        if fut:
            fut.set_result(msg)


class ServerWithReverseMCP:
    """Start a simplest agent server to support reverse mcp"""

    def __init__(
        self,
        agent: "Agent",
        host: str = "0.0.0.0",
        port: int = 8000,
    ):
        self.agent = agent

        self.host = host
        self.port = port

        self.app = FastAPI()
        # build routes for self.app
        self.build()

        self.ws_session_mgr = WebsocketSessionManager()
        self.ws_agent_mgr: dict[str, "Agent"] = {}

    def build(self):
        logger.info("Build routes for server with reverse mcp")

        class InvokeRequest(BaseModel):
            """Request model for /invoke endpoint"""

            prompt: str
            app_name: str
            user_id: str
            session_id: str

            websocket_id: str

        class InvokeResponse(BaseModel):
            """Response model for /invoke endpoint"""

            response: str

        # build agent invocation route
        @self.app.post("/invoke")
        async def invoke(payload: InvokeRequest) -> InvokeResponse:
            user_id = payload.user_id
            session_id = payload.session_id
            prompt = payload.prompt

            agent = self.ws_agent_mgr[payload.websocket_id]

            if not agent.tools:
                logger.debug("Mount fake MCPToolset to agent")

                # we hard code the mcp url with `/mcp` to obey the mcp protocol
                agent.tools.append(
                    MCPToolset(
                        connection_params=StreamableHTTPConnectionParams(
                            url=f"http://127.0.0.1:{self.port}/mcp",
                            headers={REVERSE_MCP_HEADER_KEY: payload.websocket_id},
                        ),
                    )
                )

            runner = Runner(app_name=payload.app_name, agent=agent)
            response = await runner.run(
                messages=[prompt],
                user_id=user_id,
                session_id=session_id,
            )

            return InvokeResponse(response=response)

        # build websocket endpoint
        @self.app.websocket("/ws")
        async def ws_endpoint(ws: WebSocket):
            client_id = ws.query_params.get("id")
            if not client_id:
                await ws.close(
                    code=400,
                    reason="WebSocket `id` is required like `/ws?id=my_id`",
                )
                return

            logger.info(f"Register websocket {client_id} to session manager.")
            self.ws_session_mgr.connections[client_id] = ws

            logger.info(f"Fork agent for websocket {client_id}")
            self.ws_agent_mgr[client_id] = self.agent.clone()

            await ws.accept()
            logger.info(f"Websocket {client_id} connected")

            while True:
                raw = await ws.receive_text()
                await self.ws_session_mgr.handle_ws_message(client_id, raw)

        # build the fake MPC server,
        # and intercept all requests to the client websocket client.
        @self.app.api_route("/{path:path}", methods=["GET", "POST"])
        async def mcp_proxy(path: str, request: Request):
            client_id = request.headers.get(REVERSE_MCP_HEADER_KEY)
            if not client_id:
                return Response("client id not found", status_code=400)

            ws = self.ws_session_mgr.connections.get(client_id)
            if not ws:
                return Response("websocket `client_id` not connected", status_code=503)

            body = await request.body()
            headers = dict(request.headers)
            method = request.method
            path = f"/{path}"

            payload = {
                "method": method,
                "path": path,
                "headers": headers,
                "body": body.decode(),
            }

            logger.debug(f"[Reverse mcp proxy] Request from agent: {payload}")

            resp = await self.ws_session_mgr.call_mcp_http(client_id, payload)

            logger.debug(f"[Reverse mcp proxy] Response from local: {resp}")

            return Response(
                content=resp["payload"]["body"],  # type: ignore
                status_code=resp["payload"]["status"],  # type: ignore
                headers=resp["payload"]["headers"],  # type: ignore
            )

    def run(self):
        import uvicorn

        uvicorn.run(self.app, host=self.host, port=self.port)
