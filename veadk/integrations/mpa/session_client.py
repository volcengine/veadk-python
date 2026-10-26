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

"""Self-Hosted Sandbox client using official Anthropic Python SDK (client.beta.sessions & events).

Endpoints managed via Anthropic SDK:
1. client.beta.sessions.create:
   Creates a session and enqueues work into the WorkQueue for the worker.
2. client.beta.sessions.events.send:
   Publishes ``agent.tool_use`` and ``session.status_idle`` events.
3. client.beta.sessions.events.list:
   Retrieves session events to wait for ``user.tool_result`` from workers.
"""

import json
import logging
import os
import re
import time
import uuid
from typing import Any
from urllib.parse import urlsplit

import anthropic

logger = logging.getLogger("veadk.sandbox")


def _runtime_id_from_environment() -> str:
    """Resolve the AgentKit Runtime identity without guessing platform IDs."""
    for name in ("AGENTKIT_RUNTIME_ID", "MA_RUNTIME_ID"):
        if runtime_id := os.getenv(name, "").strip():
            return runtime_id

    client_request_id = os.getenv("MODEL_AGENT_CLIENT_REQ_ID", "").strip()
    match = re.fullmatch(r"agentkit/([^/\s]+)", client_request_id)
    return match.group(1) if match else ""


class SelfHostSandboxClient:
    """Client for Managed Agents Self-Hosted Sandbox backed by official Anthropic SDK."""

    def __init__(
        self,
        base_url: str | None = None,
        environment_id: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
        bearer_token: str | None = None,
        account_id: str | None = None,
        remote_bash_tool_name: str | None = None,
        timeout: int = 300,
        trust_env: bool | None = None,
        runtime_type: str | None = None,
    ):
        self.base_url = (
            base_url
            or os.getenv("ANTHROPIC_BASE_URL")
            or os.getenv("SANDBOX_BASE_URL", "")
        ).rstrip("/")
        self.environment_id = (
            environment_id
            or os.getenv("ANTHROPIC_ENVIRONMENT_ID")
            or os.getenv("SANDBOX_ENVIRONMENT_ID", "")
        )
        self.agent_id = agent_id or os.getenv("SANDBOX_AGENT_ID", "")
        self.session_id = (
            session_id
            or os.getenv("ANTHROPIC_SESSION_ID")
            or os.getenv("SANDBOX_SESSION_ID")
        )

        raw_token = (
            bearer_token
            or os.getenv("ANTHROPIC_ENVIRONMENT_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("SANDBOX_BEARER_TOKEN")
            or os.getenv("SANDBOX_API_KEY", "")
        )
        runtime_id = _runtime_id_from_environment()
        self._identity_credentials = None
        if not raw_token and runtime_id:
            from veadk.runtime.managed_agents.identity import (
                get_runtime_credential_provider,
            )

            self._identity_credentials = get_runtime_credential_provider(
                runtime_id=runtime_id,
                region=os.getenv("VOLCENGINE_REGION")
                or os.getenv("REGION")
                or "cn-beijing",
            )
            raw_token = self._identity_credentials.get_sync()
        if raw_token.startswith("Bearer "):
            raw_token = raw_token[7:].strip()
        self.bearer_token = raw_token
        self.account_id = account_id or os.getenv("X_TOP_ACCOUNT_ID", "")
        # RuntimeType routes this worker's AgentLoop poll to a specific
        # execution pool. Empty means legacy behaviour: the server treats a
        # typeless poll as the reserved ``default`` pool.
        self.runtime_type = (
            runtime_type or os.getenv("MA_AGENT_LOOP_RUNTIME_TYPE") or ""
        ).strip()
        self.remote_bash_tool_name = remote_bash_tool_name or os.getenv(
            "SANDBOX_BASH_TOOL_NAME", "bash"
        )
        self.timeout = int(os.getenv("SANDBOX_TIMEOUT_SECONDS", str(timeout)))
        self.trust_env = trust_env

        if not self.base_url:
            raise ValueError(
                "ANTHROPIC_BASE_URL (or SANDBOX_BASE_URL) must be configured in .env or arguments."
            )
        if not self.bearer_token:
            raise ValueError(
                "ANTHROPIC_ENVIRONMENT_KEY (or SANDBOX_BEARER_TOKEN) must be configured in .env or arguments."
            )

        # The Runtime gateway needs the Managed Agents beta flag and, when
        # supplied, the Volcengine top-account routing header.
        default_headers = {
            "anthropic-beta": "managed-agents-2026-04-01",
        }
        if self.account_id:
            default_headers["X-Top-Account-Id"] = str(self.account_id)
        # Inject the AgentLoop RuntimeType routing label alongside the existing
        # auth/beta headers so every SDK helper poll carries it. ma-infra pairs
        # this with the optional ``runtime_type`` poll query and rejects a
        # conflicting pair with 400.
        if self.runtime_type:
            default_headers["X-Runtime-Type"] = self.runtime_type

        self._default_headers = default_headers
        http_client = (
            anthropic.DefaultHttpxClient(
                trust_env=False if trust_env is None else trust_env,
                event_hooks={
                    "request": [self._identity_request],
                    "response": [self._identity_response],
                },
            )
            if self._identity_credentials is not None
            else anthropic.DefaultHttpxClient(trust_env=trust_env)
            if trust_env is not None
            else None
        )
        self.client = anthropic.Anthropic(
            base_url=self.base_url,
            auth_token=self.bearer_token,
            default_headers=default_headers,
            timeout=float(self.timeout),
            http_client=http_client,
        )

    def _set_gateway_header(self, request: Any, key: str) -> None:
        # SDK Work sub-clients deliberately strip parent auth headers. Apply
        # gateway auth at transport send time so their scoped Bearer survives.
        expected = urlsplit(self.base_url)
        actual = urlsplit(str(request.url))
        if (actual.scheme, actual.hostname, actual.port) != (
            expected.scheme,
            expected.hostname,
            expected.port,
        ):
            from veadk.runtime.managed_agents.identity import RuntimeIdentityError

            raise RuntimeIdentityError("authentication_failed", False)
        request.headers["x-api-key"] = key
        if request.headers.get("Authorization") == "Bearer " + self.bearer_token:
            del request.headers["Authorization"]

    def _identity_request(self, request: Any) -> None:
        assert self._identity_credentials is not None
        self._set_gateway_header(request, self._identity_credentials.get_sync())

    async def _identity_async_request(self, request: Any) -> None:
        assert self._identity_credentials is not None
        self._set_gateway_header(request, await self._identity_credentials.get())

    def _identity_response(self, response: Any) -> None:
        if response.status_code in {401, 403}:
            assert self._identity_credentials is not None
            self._identity_credentials.invalidate()

    async def _identity_async_response(self, response: Any) -> None:
        self._identity_response(response)

    def create_async_client(self) -> anthropic.AsyncAnthropic:
        """Create an async SDK client for the Agent Loop event stream."""
        http_client = (
            anthropic.DefaultAsyncHttpxClient(
                trust_env=False if self.trust_env is None else self.trust_env,
                event_hooks={
                    "request": [self._identity_async_request],
                    "response": [self._identity_async_response],
                },
            )
            if self._identity_credentials is not None
            else anthropic.DefaultAsyncHttpxClient(trust_env=self.trust_env)
            if self.trust_env is not None
            else None
        )
        return anthropic.AsyncAnthropic(
            base_url=self.base_url,
            auth_token=self.bearer_token,
            default_headers=self._default_headers,
            timeout=float(self.timeout),
            http_client=http_client,
        )

    def create_session(
        self,
        title: str = "VeADK Self-Hosted Sandbox Session",
    ) -> dict[str, Any]:
        """POST /v1/sessions via Anthropic SDK (client.beta.sessions.create).

        This only creates the session. A real ``user.message`` event causes the
        server control plane to enqueue the corresponding WorkItem.
        """
        if not self.agent_id or not self.environment_id:
            raise ValueError(
                "Session creation requires configured agent_id and environment_id"
            )
        sess = self.client.beta.sessions.create(
            agent=self.agent_id,
            environment_id=self.environment_id,
            title=title,
            # Fix the session's AgentLoop RuntimeType at creation when this
            # client is configured with one; ma-infra snapshots it and never
            # lets successor/recovery Work drift to another type.
            extra_body=(
                {"runtime_type": self.runtime_type} if self.runtime_type else None
            ),
        )
        self.session_id = sess.id
        logger.info(
            "Session %s created on remote Runtime via Anthropic SDK.", self.session_id
        )
        if hasattr(sess, "model_dump"):
            return sess.model_dump(warnings=False)
        return {
            "id": sess.id,
            "environment_id": self.environment_id,
            "agent": self.agent_id,
        }

    def post_events(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        """POST /v1/sessions/{session_id}/events via Anthropic SDK (client.beta.sessions.events.send).

        Dispatches tool calls and tool results into the Session event stream.
        """
        if not self.session_id:
            self.create_session()

        from veadk.runtime.managed_agents.events import (
            trace_events,
            trace_send_response,
        )

        trace_events("sent", "send", self.session_id, events)
        response = self.client.beta.sessions.events.send(
            session_id=self.session_id,
            events=events,
        )
        trace_send_response(self.session_id, response)
        if hasattr(response, "model_dump"):
            return response.model_dump(warnings=False)
        return {"status": "ok"}

    def send_tool_result(
        self, tool_use_id: str, content: str, is_error: bool = False
    ) -> dict[str, Any]:
        """Send tool execution result to POST /v1/sessions/{session_id}/events."""
        event = {
            "type": "user.tool_result",
            "tool_use_id": tool_use_id,
            "content": [{"type": "text", "text": content}],
            "is_error": is_error,
        }
        return self.post_events([event])

    def list_events(
        self,
        *,
        limit: int = 100,
        order: str = "asc",
    ) -> list[dict[str, Any]]:
        """Read and normalize events from GET /v1/sessions/{id}/events via Anthropic SDK."""
        if not self.session_id:
            raise RuntimeError("Cannot read events before a Session is created.")

        page = self.client.beta.sessions.events.list(
            session_id=self.session_id,
            limit=limit,
            order=order,
        )
        events: list[dict[str, Any]] = []
        from veadk.runtime.managed_agents.events import trace_event

        for item in page.data:
            trace_event("received", "list", self.session_id, item)
            if hasattr(item, "model_dump"):
                d = item.model_dump(warnings=False)
            elif isinstance(item, dict):
                d = dict(item)
            else:
                d = {
                    "id": getattr(item, "id", None),
                    "type": getattr(item, "type", None),
                    "name": getattr(item, "name", None),
                    "input": getattr(item, "input", None),
                    "content": getattr(item, "content", None),
                    "is_error": getattr(item, "is_error", False),
                    "tool_use_id": getattr(item, "tool_use_id", None),
                }
            events.append(d)
        return events

    def post_status_idle(self, stop_reason: str = "end_turn") -> None:
        """Publish a ``session.status_idle`` event so workers know the turn ended and can release their lease."""
        if not self.session_id:
            return
        try:
            self.post_events(
                [
                    {
                        "type": "session.status_idle",
                        "stop_reason": {
                            "type": stop_reason,
                        },
                    }
                ]
            )
            logger.info(
                "Session %s marked status_idle (%s).", self.session_id, stop_reason
            )
        except Exception as e:  # noqa: BLE001 -- idle notification is best effort
            logger.warning(
                "Failed to post session.status_idle for %s: %s", self.session_id, e
            )

    def dispatch_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        dispatch_id: str = "",
    ) -> dict[str, Any]:
        """Dispatch the registered tool name and JSON input without shell conversion."""
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise ValueError("tool_name must be nonempty")
        if not isinstance(arguments, dict):
            raise TypeError("tool input must be an object")
        if not self.session_id:
            self.create_session()
        payload = dict(arguments)
        timeout_seconds = float(self.timeout)
        if tool_name == "bash":
            # Only the bash tool has an execution timeout in the native schema.
            if payload.get("timeout_ms") is None:
                payload["timeout_ms"] = int(timeout_seconds * 1000)
            timeout_seconds = self._positive_timeout(payload["timeout_ms"]) / 1000
        tool_use_id = dispatch_id or f"toolu_{uuid.uuid4().hex}"
        self.post_events(
            [
                {
                    "type": "agent.tool_use",
                    "id": tool_use_id,
                    "name": tool_name,
                    "input": payload,
                }
            ]
        )
        return self._wait_for_tool_result(
            timeout=timeout_seconds + 60,
            tool_use_id=tool_use_id,
            dispatch_id=dispatch_id or tool_use_id,
        )

    def execute_command(
        self,
        command: str,
        *,
        timeout: float | None = None,
        dispatch_id: str = "",
    ) -> dict[str, Any]:
        """Convenience entry point for a native bash invocation."""
        return self.dispatch_tool(
            self.remote_bash_tool_name,
            {
                "command": command,
                "timeout_ms": int(
                    self._positive_timeout(
                        float(self.timeout) if timeout is None else timeout
                    )
                    * 1000
                ),
            },
            dispatch_id=dispatch_id,
        )

    def _wait_for_tool_result(
        self,
        *,
        timeout: float,
        tool_use_id: str,
        dispatch_id: str,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            events = self.list_events(limit=100, order="asc")
            for event in events:
                event_type = str(event.get("type") or "")
                if event_type not in {"agent.tool_result", "user.tool_result"}:
                    continue
                result_tool_use_id = str(event.get("tool_use_id") or "")
                if result_tool_use_id == tool_use_id:
                    result = self._normalize_tool_result(
                        event,
                        tool_use_id=tool_use_id,
                        dispatch_id=dispatch_id,
                    )
                    if event_type == "user.tool_result":
                        self.post_events(
                            [
                                {
                                    "type": "agent.tool_result",
                                    "tool_use_id": tool_use_id,
                                    "content": event.get("content") or "",
                                    "is_error": bool(event.get("is_error")),
                                }
                            ]
                        )
                    return result
            time.sleep(0.5)

        raise TimeoutError(
            f"Timed out after {timeout:g}s waiting for tool result {tool_use_id}."
        )

    @staticmethod
    def _positive_timeout(value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ValueError("timeout must be greater than zero")
        return float(value)

    def _normalize_tool_result(
        self,
        event: dict[str, Any],
        *,
        tool_use_id: str,
        dispatch_id: str,
    ) -> dict[str, Any]:
        content = self._content_text(event.get("content"))
        match = re.match(r"^exit=(-?\d+)\n([\s\S]*)$", content)
        if match:
            exit_code = int(match.group(1))
            stdout = match.group(2)
        else:
            exit_code = 1 if event.get("is_error") else 0
            stdout = content
        return {
            "dispatch_id": dispatch_id,
            "tool_use_id": tool_use_id,
            "environment_id": self.environment_id,
            "session_id": self.session_id,
            "status": "failed" if exit_code else "completed",
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": "",
            "content": event.get("content"),
            "is_error": bool(event.get("is_error")),
        }

    @staticmethod
    def _event_seq(event: dict[str, Any]) -> int:
        try:
            return int(event.get("_seq", 0) or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _content_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
                elif isinstance(block, str):
                    parts.append(block)
            return "\n".join(part for part in parts if part)
        if content is None:
            return ""
        return json.dumps(content, ensure_ascii=False)
