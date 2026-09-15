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


"""A native ADK sub-agent backed by an AgentKit Skill or CodeEnv session."""

from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import aclosing
from typing import Literal

from google.adk.agents.base_agent import BaseAgent
from google.adk.events import Event
from google.genai import types
from pydantic import Field, PrivateAttr, SecretStr

from veadk.agents._remote_sandbox.client import create_agentkit_client
from veadk.agents._remote_sandbox.timeout import timeout
from veadk.agents._remote_sandbox.session import ensure_agentkit_session_lease
from veadk.tools.builtin_tools._agentkit import (
    get_agentkit_endpoint_config,
    resolve_agentkit_tool_id,
)


def binding_key(*parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


class SandboxAgentError(RuntimeError):
    """A safe diagnostic suitable for returning to the caller."""


class AgentkitRemoteSandboxAgent(BaseAgent):
    """Register in ``Agent(sub_agents=[...])``; no network during construction.

    Explicit tool_type wins over discovery. Private tools require an explicit
    compatible type. endpoint is an optional pre-provisioned session URL for
    local testing; it requires an explicit type and bypasses the control plane.
    Remote calls/results are observation events, never locally executed tools.
    """

    tool_id: str | None = None
    tool_type: Literal["Skill", "CodeEnv"] | None = None
    request_timeout: float = Field(default=900, gt=0, lt=86000)
    expiry_buffer: float = Field(default=90, ge=0, lt=86400)
    ready_timeout: float = Field(default=120, gt=0)
    ttl: int = Field(default=1800, ge=60, le=86400)
    prefer_internal_endpoint: bool = False
    endpoint: str | None = Field(default=None, repr=False)
    api_key: SecretStr | None = Field(default=None, repr=False, exclude=True)
    _types: dict = PrivateAttr(default_factory=dict)
    _contexts: dict = PrivateAttr(default_factory=dict)
    _locks: dict = PrivateAttr(default_factory=dict)
    _type_lock: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)

    def model_post_init(self, context):
        super().model_post_init(context)
        if self.endpoint and self.tool_type is None:
            raise ValueError("endpoint requires explicit tool_type")
        if self.request_timeout + self.expiry_buffer + 2 * self.ready_timeout >= 86400:
            raise ValueError(
                "Execution and readiness budget must fit within 86400 seconds"
            )

    def _discover_type(self, tool_id, state):
        from agentkit.sdk.tools.types import GetToolRequest

        result = create_agentkit_client(state).get_tool(GetToolRequest(ToolId=tool_id))
        if result.tool_type not in {"Skill", "CodeEnv"}:
            raise SandboxAgentError(
                "GetTool must return Skill or CodeEnv; specify tool_type explicitly for a compatible custom tool"
            )
        return result.tool_type

    async def _resolve(self, ctx, logical):
        if self.endpoint:
            return self.tool_type, self.endpoint, binding_key(self.endpoint), None
        tool_id = self.tool_id or resolve_agentkit_tool_id()
        state = dict(ctx.session.state)
        kind = self.tool_type
        if kind is None:
            # Identity-scoped cache: never share discovery across application users.
            cache_key = (
                ctx.app_name,
                ctx.user_id,
                tool_id,
                get_agentkit_endpoint_config(),
            )
            async with self._type_lock:
                kind = self._types.get(cache_key)
                if kind is None:
                    kind = await asyncio.to_thread(self._discover_type, tool_id, state)
                    if len(self._types) >= 256:
                        self._types.clear()
                    self._types[cache_key] = kind
        lease = await asyncio.to_thread(
            ensure_agentkit_session_lease,
            tool_id=tool_id,
            tool_user_session_id=logical,
            tool_state=state,
            ttl=self.ttl,
            min_remaining_seconds=self.request_timeout
            + self.expiry_buffer
            + self.ready_timeout,
            ready_timeout=self.ready_timeout,
        )
        return (
            kind,
            lease.select_endpoint(
                prefer_internal_endpoint=self.prefer_internal_endpoint
            ),
            lease.session_id,
            lease,
        )

    async def _headers(self, ctx):
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key.get_secret_value()
        if ctx.credential_service:
            from google.adk.agents.callback_context import CallbackContext
            from veadk.utils.auth import build_auth_config

            credential = await ctx.credential_service.load_credential(
                auth_config=build_auth_config(
                    credential_key="inbound_auth",
                    auth_method="header",
                    header_scheme="bearer",
                ),
                callback_context=CallbackContext(ctx),
            )
            if credential:
                token = credential.api_key
                if not token and credential.http and credential.http.credentials:
                    token = credential.http.credentials.token
                if not token and credential.oauth2:
                    token = credential.oauth2.access_token
                if token:
                    headers["inbound_auth"] = token
        return headers

    async def _run_async_impl(self, ctx):
        from veadk.agents._remote_sandbox.code import code_events
        from veadk.agents._remote_sandbox.skill import skill_events

        logical = binding_key(
            ctx.app_name,
            ctx.user_id,
            ctx.session.id,
            self.name,
            self.tool_id,
            self.endpoint,
        )
        if logical not in self._locks:
            if len(self._locks) >= 256:
                raise SandboxAgentError(
                    "Agent session capacity reached; create a new agent instance"
                )
            self._locks[logical] = asyncio.Lock()
        lock = self._locks[logical]
        if lock.locked():
            raise SandboxAgentError(
                "A sandbox invocation is already active for this session"
            )
        async with lock:
            try:
                async with timeout(self.ready_timeout * 2 + 60):
                    kind, endpoint, physical, lease = await self._resolve(ctx, logical)
                    headers = await self._headers(ctx)
                user_event = next(
                    (
                        e
                        for e in reversed(ctx.session.events)
                        if e.author == "user" and e.content
                    ),
                    None,
                )
                content = user_event.content if user_event else ctx.user_content
                if not content or not content.parts:
                    raise SandboxAgentError("A user task is required")
                task = "\n".join(p.text for p in content.parts if p.text)
                if not task.strip():
                    raise SandboxAgentError(
                        "This sandbox entry currently requires a text task"
                    )
                binding = binding_key(logical, physical)
                turn_key = binding_key(binding, ctx.invocation_id)
                # Only a physical-session-bound context can be reused.
                previous = self._contexts.get(logical)
                if previous is None or previous.get("physical") != physical:
                    previous = {"physical": physical}
                    self._contexts[logical] = previous
                backend = code_events if kind == "CodeEnv" else skill_events
                async with timeout(self.request_timeout + self.ready_timeout):
                    async with aclosing(
                        backend(
                            agent=self,
                            ctx=ctx,
                            endpoint=endpoint,
                            headers=headers,
                            binding=binding,
                            turn_key=turn_key,
                            task=task,
                            context=previous,
                            lease=lease,
                        )
                    ) as stream:
                        async for event in stream:
                            yield event
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                message = (
                    str(exc)
                    if isinstance(exc, SandboxAgentError)
                    else f"Sandbox invocation failed ({type(exc).__name__}); execution may be unconfirmed"
                )
                yield Event(
                    author=self.name,
                    invocation_id=ctx.invocation_id,
                    branch=ctx.branch,
                    error_message=message,
                    content=types.Content(
                        role="model", parts=[types.Part(text=message)]
                    ),
                )
