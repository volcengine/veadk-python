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
from typing import TYPE_CHECKING, Any, Optional

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.responses import StreamingResponse
from google.adk.agents.run_config import StreamingMode
from google.adk.artifacts import InMemoryArtifactService
from google.adk.cli.adk_web_server import RunAgentRequest
from google.adk.runners import Runner as GoogleRunner, RunConfig
from google.adk.sessions import InMemorySessionService, Session
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.utils.context_utils import Aclosing
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

        self.artifact_service = InMemoryArtifactService()

        # build routes for self.app
        self.build()

        self.ws_session_mgr = WebsocketSessionManager()
        self.ws_agent_mgr: dict[str, "Agent"] = {}
        self.ws_session_service_mgr: dict[str, "InMemorySessionService"] = {}

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

            # Parse filters from query params, comma-separated string
            filters_str = ws.query_params.get("filters")
            filters = None
            if filters_str:
                filters = [t.strip() for t in filters_str.split(",") if t.strip()]

            logger.info(f"Register websocket {client_id} to session manager.")
            self.ws_session_mgr.connections[client_id] = ws

            logger.info(f"Fork agent for websocket {client_id}")
            agent = self.agent.clone()

            logger.info(
                f"clone agent \n model_name={agent.model_name}\n instruction={agent.instruction}\n"
            )

            # Mount MCPToolset when creating agent
            mcp_toolset_url = f"http://127.0.0.1:{self.port}/mcp"
            mcp_toolset_headers = {REVERSE_MCP_HEADER_KEY: client_id}
            logger.debug(f"Mount MCPToolset to agent for websocket {client_id}")
            agent.tools.append(
                MCPToolset(
                    connection_params=StreamableHTTPConnectionParams(
                        url=mcp_toolset_url,
                        headers=mcp_toolset_headers,
                    ),
                    tool_filter=filters,
                )
            )
            self.ws_agent_mgr[client_id] = agent

            logger.info(f"Create session service for websocket {client_id}")
            self.ws_session_service_mgr[client_id] = InMemorySessionService()

            await ws.accept()
            logger.info(f"Websocket {client_id} connected")

            try:
                while True:
                    raw = await ws.receive_text()
                    logger.debug(f"ws.receive_text() = {raw}")
                    await self.ws_session_mgr.handle_ws_message(client_id, raw)
            except Exception as e:
                logger.warning(f"client {client_id} web socket connection closed: {e}")

        class CreateSessionRequest(BaseModel):
            state: Optional[dict[str, Any]] = None
            session_id: Optional[str] = None
            websocket_id: str

        class RunAgentRequestWithWsId(RunAgentRequest):
            websocket_id: str

        def _get_session_service(websocket_id: str) -> InMemorySessionService:
            """Get session service for the websocket client."""
            if websocket_id not in self.ws_session_service_mgr:
                raise HTTPException(
                    status_code=404, detail=f"WebSocket client {websocket_id} not found"
                )
            return self.ws_session_service_mgr[websocket_id]

        @self.app.post(
            "/apps/{app_name}/users/{user_id}/sessions",
            response_model_exclude_none=True,
        )
        async def create_session(
            app_name: str,
            user_id: str,
            req: CreateSessionRequest,
        ) -> Session:
            """Create a new session."""
            session_id = req.session_id if req.session_id else str(uuid.uuid4())
            session = Session(
                app_name=app_name,
                user_id=user_id,
                id=session_id,
                state=req.state if req.state else {},
            )
            session_service = _get_session_service(req.websocket_id)
            await session_service.create_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
                state=req.state if req.state else {},
            )
            logger.info(
                f"Created session: {session_id} for user {user_id} in app {app_name}"
            )
            return session

        @self.app.post(
            "/apps/{app_name}/users/{user_id}/sessions/{session_id}",
            response_model_exclude_none=True,
        )
        async def create_session_with_id(
            app_name: str,
            user_id: str,
            session_id: str,
            req: CreateSessionRequest,
        ) -> Session:
            """Create a session with specific ID."""
            session_service = _get_session_service(req.websocket_id)
            await session_service.create_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
                state=req.state if req.state else {},
            )
            session = Session(
                app_name=app_name,
                user_id=user_id,
                id=session_id,
                state=req.state if req.state else {},
            )
            logger.info(f"Created session with ID: {session_id} for user {user_id}")
            return session

        @self.app.post("/run_sse")
        async def run_agent_sse(req: RunAgentRequestWithWsId) -> StreamingResponse:
            """Run agent with SSE streaming."""
            session_service = _get_session_service(req.websocket_id)

            # Get session
            session = await session_service.get_session(
                app_name=req.app_name,
                user_id=req.user_id,
                session_id=req.session_id,
            )
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

            # Get agent for this websocket
            if req.websocket_id in self.ws_agent_mgr:
                agent = self.ws_agent_mgr[req.websocket_id]
                logger.debug(f"Using agent from websocket {req.websocket_id}")
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"WebSocket client {req.websocket_id} not found",
                )

            # Create runner
            runner = GoogleRunner(
                agent=agent,
                app_name=req.app_name,
                session_service=session_service,
                artifact_service=self.artifact_service,
            )

            # Determine streaming mode from request
            stream_mode = StreamingMode.SSE if req.streaming else StreamingMode.NONE

            async def event_generator():
                try:
                    async with Aclosing(
                        runner.run_async(
                            user_id=req.user_id,
                            session_id=req.session_id,
                            new_message=req.new_message,
                            state_delta=req.state_delta,
                            run_config=RunConfig(streaming_mode=stream_mode),
                            invocation_id=req.invocation_id,
                        )
                    ) as agen:
                        async for event in agen:
                            # ADK Web renders artifacts from `actions.artifactDelta`
                            # during part processing *and* during action processing
                            # 1) the original event with `artifactDelta` cleared (content)
                            # 2) a content-less "action-only" event carrying `artifactDelta`
                            events_to_stream = [event]
                            if (
                                event.actions.artifact_delta
                                and event.content
                                and event.content.parts
                            ):
                                content_event = event.model_copy(deep=True)
                                content_event.actions.artifact_delta = {}
                                artifact_event = event.model_copy(deep=True)
                                artifact_event.content = None
                                events_to_stream = [content_event, artifact_event]

                            for event_to_stream in events_to_stream:
                                sse_event = event_to_stream.model_dump_json(
                                    exclude_none=True, by_alias=True
                                )
                                logger.debug(f"SSE event: {sse_event}")
                                yield f"data: {sse_event}\n\n"
                except Exception as e:
                    logger.exception(f"Error in event_generator: {e}")
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
            )

        # build the fake MPC server,
        # and intercept all requests to the client websocket client.
        # NOTE: This catch-all route must be defined LAST
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

            # Filter hop-by-hop headers to avoid Content-Length mismatch
            headers = resp["payload"]["headers"]
            hop_by_hop_headers = {
                "content-length",
                "transfer-encoding",
                "connection",
                "keep-alive",
                "proxy-authenticate",
                "proxy-authorization",
                "te",
                "trailers",
                "upgrade",
            }
            filtered_headers = {
                k: v for k, v in headers.items() if k.lower() not in hop_by_hop_headers
            }

            return Response(
                content=resp["payload"]["body"],  # type: ignore
                status_code=resp["payload"]["status"],  # type: ignore
                headers=filtered_headers,  # type: ignore
            )

    def run(self):
        import uvicorn

        uvicorn.run(self.app, host=self.host, port=self.port)
