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

"""Local HTTP/SSE smoke test for the VeADK Managed Agents Loop.

This script uses the installed Managed Agents package and public Anthropic SDK.
It uses no real credentials, model, or remote service.
"""

from __future__ import annotations

import json
import asyncio
import threading
from typing import Any, ClassVar
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from types import SimpleNamespace
from urllib.parse import urlparse

from typing_extensions import override

from managed_agent_loop import ManagedAgentsLoop
from sandbox_client import SelfHostSandboxClient

SESSION_ID = "session_veadk_local"


class LocalSessionEvents(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    events: ClassVar[list[dict[str, Any]]] = []
    changed: ClassVar[threading.Condition] = threading.Condition()

    @override
    def log_message(self, format: str, *args: object) -> None:
        return

    def do_POST(self) -> None:
        if urlparse(self.path).path != f"/v1/sessions/{SESSION_ID}/events":
            self.send_error(404)
            return
        length = int(self.headers.get("content-length", "0"))
        payload = json.loads(self.rfile.read(length))
        persisted: list[dict[str, Any]] = []
        with self.changed:
            for event in payload["events"]:
                item = dict(event)
                item.setdefault("id", f"event_{len(self.events) + 1}")
                item["processed_at"] = datetime.now(timezone.utc).isoformat()
                self.events.append(item)
                persisted.append(item)
            self.changed.notify_all()
        self._json({"data": persisted})

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == f"/v1/sessions/{SESSION_ID}/events":
            with self.changed:
                events = [dict(event) for event in self.events]
            self._json({"data": events, "has_more": False})
            return
        if path != f"/v1/sessions/{SESSION_ID}/events/stream":
            self.send_error(404)
            return

        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("cache-control", "no-cache")
        self.send_header("connection", "close")
        self.end_headers()
        cursor = 0
        while True:
            with self.changed:
                if cursor >= len(self.events):
                    self.changed.wait(timeout=10)
                if cursor >= len(self.events):
                    return
                pending = [dict(event) for event in self.events[cursor:]]
                cursor += len(pending)
            for event in pending:
                frame = (
                    f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode()
                )
                self.wfile.write(frame)
                self.wfile.flush()
                if event["type"] in {"session.status_idle", "session.error"}:
                    return

    def _json(self, value: object) -> None:
        body = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class LocalSessionService:
    def __init__(self) -> None:
        self.session: object | None = None

    async def get_session(self, **kwargs: object) -> object | None:
        return self.session

    async def create_session(self, **kwargs: object) -> object:
        self.session = object()
        return self.session


class LocalRunner:
    app_name = "veadk-managed-agent-local-test"

    def __init__(self) -> None:
        self.session_service = LocalSessionService()

    async def run_async(self, **kwargs: object):
        message = kwargs["new_message"]
        prompt = message.parts[0].text
        yield SimpleNamespace(
            partial=False,
            content=SimpleNamespace(
                parts=[SimpleNamespace(text="Thinking locally", thought=True)]
            ),
            usage_metadata=None,
            get_function_calls=lambda: [],
        )
        yield SimpleNamespace(
            partial=False,
            content=SimpleNamespace(
                parts=[SimpleNamespace(text=str(prompt).upper(), thought=False)]
            ),
            usage_metadata=SimpleNamespace(
                prompt_token_count=3,
                candidates_token_count=3,
                cached_content_token_count=0,
            ),
            get_function_calls=lambda: [],
        )


def main() -> None:
    LocalSessionEvents.events = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), LocalSessionEvents)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    client = SelfHostSandboxClient(
        base_url=f"http://127.0.0.1:{server.server_port}",
        environment_id="env_local",
        agent_id="agent_local",
        session_id=SESSION_ID,
        bearer_token="local-test-token",  # gitleaks:allow loopback test credential
        trust_env=False,
    )

    loop = ManagedAgentsLoop(runner=LocalRunner(), session_client=client)
    loop_thread = threading.Thread(
        target=lambda: asyncio.run(loop.run(max_turns=1)), daemon=True
    )
    loop_thread.start()
    try:
        client.client.beta.sessions.events.send(
            SESSION_ID,
            events=[
                {
                    "type": "user.message",
                    "content": [{"type": "text", "text": "hello veadk loop"}],
                }
            ],
        )
        loop_thread.join(timeout=10)
        if loop_thread.is_alive():
            raise RuntimeError("VeADK Agent Loop did not finish")

        event_types = [event["type"] for event in client.list_events()]
        expected = [
            "user.message",
            "session.status_running",
            "span.model_request_start",
            "agent.thinking",
            "agent.message",
            "span.model_request_end",
            "session.status_idle",
        ]
        if event_types != expected:
            raise RuntimeError(f"Unexpected events: {event_types!r}")
        print("VeADK Managed Agents Loop local test passed.")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
