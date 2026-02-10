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

import json

import httpx
import websockets

from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class ClientWithReverseMCP:
    def __init__(
        self,
        ws_url: str,
        mcp_server_url: str,
        client_id: str,
        mcp_tool_filter: list[str] | None = None,
    ):
        """Start a client with reverse mcp,

        Args:
            ws_url: The url of the websocket server (cloud). Like example.com:8000
            mcp_server_url: The url of the mcp server (local).
            client_id: The client id for the websocket connection.
            mcp_tool_filter: Optional list of tool names to filter. If None, all tools are available.
        """
        self.ws_url = f"ws://{ws_url}/ws?id={client_id}"
        if mcp_tool_filter:
            self.ws_url += f"&mcp_tool_filter={','.join(mcp_tool_filter)}"
        self.mcp_server_url = mcp_server_url

        # set timeout for httpx client
        httpx.Timeout(
            connect=10.0,
            read=None,
            write=10.0,
            pool=10.0,
        )

    async def start(self):
        async with httpx.AsyncClient(base_url=self.mcp_server_url) as http:
            async with websockets.connect(self.ws_url) as ws:
                logger.info(f"Connected to cloud {self.ws_url}")

                async for raw in ws:
                    msg = json.loads(raw)
                    if msg["type"] != "http_request":
                        continue

                    req = msg["payload"]

                    logger.info(f"--- Recv {req} ---")

                    if (
                        req["method"] == "GET"
                        and "text/event-stream" in req["headers"]["accept"]
                    ):
                        logger.info("Use streamable request")
                        # streamable request

                        async with http.stream(
                            method=req["method"],
                            url=req["path"],
                            headers=req["headers"],
                            content=req["body"],
                        ) as resp:
                            reply = {
                                "id": msg["id"],
                                "type": "http_response",
                                "payload": {
                                    "status": resp.status_code,
                                    "headers": dict(resp.headers),
                                    "body": "",
                                },
                            }
                            await ws.send(json.dumps(reply))

                            if req["body"]:
                                # if body is an empty string, it represents a subscription request, no need to iterate over chunks
                                async for chunk in resp.aiter_bytes():
                                    if chunk:
                                        await ws.send(
                                            json.dumps(
                                                {
                                                    "id": msg["id"],
                                                    "type": "http_response_chunk",
                                                    "payload": {
                                                        "status": resp.status_code,
                                                        "headers": dict(resp.headers),
                                                        "body": chunk.decode(
                                                            "utf-8",
                                                            errors="ignore",
                                                        ),
                                                    },
                                                }
                                            )
                                        )
                    else:
                        # non-streamable request
                        logger.info("Use non-streamable request")
                        resp = await http.request(
                            method=req["method"],
                            url=req["path"],
                            headers=req["headers"],
                            content=req["body"],
                        )
                        reply = {
                            "id": msg["id"],
                            "type": "http_response",
                            "payload": {
                                "status": resp.status_code,
                                "headers": dict(resp.headers),
                                "body": resp.text,
                            },
                        }
                        await ws.send(json.dumps(reply))
