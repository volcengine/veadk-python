# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
# SPDX-License-Identifier: Apache-2.0
"""AgentKit CUA stdio Toolset. The independently installed MCP package owns provisioning."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import weakref
from datetime import timedelta

from google.adk.tools.base_toolset import BaseToolset
from google.adk.events import Event, EventActions
from google.adk.tools.mcp_tool.mcp_session_manager import (
    MCPSessionManager,
    StdioConnectionParams,
)
from google.adk.tools.mcp_tool.mcp_tool import McpTool
from mcp import StdioServerParameters, types
from google.genai import types as genai_types

_META_KEY = "veadk/cua"
_FORWARD_ENV = (
    "VOLCENGINE_ACCESS_KEY",
    "VOLCENGINE_SECRET_KEY",
    "VOLCENGINE_SESSION_TOKEN",
    "AGENTKIT_TOOL_TTL",
    "CUA_ALLOW_CREATE",
    "UV_CACHE_DIR",
    "UV_INDEX_URL",
    "UV_OFFLINE",
)


class _ComputerTool(McpTool):
    def __init__(self, definition, owner):
        super().__init__(mcp_tool=definition, mcp_session_manager=owner._manager)
        self._owner = owner
        self._batch_available = False

    async def run_async(self, *, args, tool_context):
        # Deliberately bypass McpTool's transport retry: a desktop mutation may
        # have completed before a broken connection/timeout becomes visible.
        if getattr(tool_context, "_veadk_parallel_tool_call_count", 1) > 1:
            return self._serial_rejection()
        for event in reversed(tool_context.session.events):
            content = event.content
            if content and content.role == "model":
                calls = [
                    p.function_call for p in content.parts or [] if p.function_call
                ]
                if len(calls) > 1:
                    return self._serial_rejection()
                break
        meta = self._owner._metadata(tool_context)
        try:
            session = await asyncio.wait_for(self._owner._manager.create_session(), 30)
            response = await session.call_tool(
                self.name,
                args,
                meta=meta,
                read_timeout_seconds=timedelta(seconds=self._owner.timeout),
            )
        except Exception:
            return {
                "isError": True,
                "content": [
                    {
                        "type": "text",
                        "text": "CUA MCP transport failed; outcome may be unknown. Operation was not retried.",
                    }
                ],
            }
        binding = self._owner._response_binding(response, meta)
        if binding is not None:
            # Save even on action errors: the instance may already have been
            # created. State deltas are persisted by the normal tool event.
            tool_context.state[self._owner.binding_state_key(tool_context)] = binding
        result = response.model_dump(exclude_none=True, mode="json")
        result.pop("meta", None)
        result.pop("_meta", None)
        # ADK extracts typed media parts; raw MCP base64 dictionaries remain text.
        for index, block in enumerate(response.content):
            if isinstance(block, types.ImageContent):
                result["content"][index] = genai_types.Part.from_bytes(
                    data=base64.b64decode(block.data, validate=True),
                    mime_type=block.mimeType,
                )
        return result

    def _serial_rejection(self):
        message = (
            "This CUA call was not executed: multiple tool calls in one model response "
            "are rejected. Submit one tool call at a time and wait for its result. "
        )
        if self._batch_available:
            message += (
                "For a known ordered sequence of supported desktop input actions, submit "
                "one cua_actions_batch call with actions containing action_type and the "
                "matching parameters (not MCP tool names). Do not put run_code, browser "
                "lifecycle, app/process, recording or script tools inside the batch. "
                "If the next step depends on a screenshot/result, use separate turns. "
            )
        message += (
            "This rejection covers only this CUA call, not other tools in the same "
            "response; they may have executed. Inspect their results before proceeding."
        )
        return {
            "isError": True,
            "content": [{"type": "text", "text": message}],
            "structuredContent": {
                "code": "CUA_MULTIPLE_TOOL_CALLS_REJECTED",
                "executed": False,
                "scope": "this_cua_call",
                "message": message,
            },
        }


class ComputerUseToolset(BaseToolset):
    """Per-request context, no global current session and no model routing arguments.

    The caller owns the returned Toolset and must await ``close()`` on Runtime
    shutdown. Use one Toolset per fixed ToolId/region/credential namespace.
    Successful bindings are persisted through ADK ToolContext state deltas.
    """

    def __init__(
        self,
        *,
        connection_params: StdioServerParameters,
        tool_id: str,
        region: str = "cn-beijing",
        tool_filter: list[str] | None = None,
        timeout: float = 120,
    ):
        super().__init__(tool_filter=tool_filter)
        if not re.fullmatch(r"t-[A-Za-z0-9_-]+", tool_id):
            raise ValueError("A valid AgentKit ToolId is required")
        if not 1 <= timeout <= 300:
            raise ValueError("CUA request timeout must be between 1 and 300 seconds")
        self._use_invocation_cache = False
        self._discovery_failures = {}
        self._prepare_locks = weakref.WeakValueDictionary()
        self._catalogs = {}
        self.tool_id, self.region, self.timeout = tool_id, region, timeout
        suffix = hashlib.sha256(f"{region}:{tool_id}".encode()).hexdigest()[:16]
        self.state_key = f"veadk_cua_binding_{suffix}"
        env = dict(connection_params.env or {})
        configured = env.get("AGENTKIT_TOOL_ID_CUA") or env.get("AGENTKIT_TOOL_ID")
        if configured and configured != tool_id:
            raise ValueError("MCP subprocess ToolId must match Toolset ToolId")
        if env.get("AGENTKIT_TOOL_REGION", region) != region:
            raise ValueError("MCP subprocess region must match Toolset region")
        env.update(AGENTKIT_TOOL_ID_CUA=tool_id, AGENTKIT_TOOL_REGION=region)
        params = connection_params.model_copy(update={"env": env})
        self._manager = MCPSessionManager(
            StdioConnectionParams(server_params=params, timeout=30)
        )

    def binding_state_key(self, ctx):
        """Use a distinct state entry for each agent in a shared ADK session."""
        suffix = hashlib.sha256(ctx.agent_name.encode()).hexdigest()[:16]
        return f"{self.state_key}_{suffix}"

    def _metadata(self, ctx):
        if ctx is None:
            raise ValueError(
                "ComputerUseToolset requires a real ADK invocation context"
            )
        for event in ctx.session.events:
            content = event.content
            calls = (
                [p.function_call for p in content.parts or [] if p.function_call]
                if content
                else []
            )
            if sum(call.name == "run_code" for call in calls) > 1:
                raise ValueError(
                    "Parallel run_code history cannot identify one desktop; start a serial session"
                )
        key = f"{ctx.agent_name}_{ctx.user_id}_{ctx.session.id}"
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", key):
            raise ValueError(
                "UserSessionId must match AgentKit limits; no automatic key rewriting"
            )
        binding = ctx.state.get(self.binding_state_key(ctx))
        route = {"user_session_id": key}
        if binding is not None:
            if not isinstance(binding, dict) or binding.get("user_session_id") != key:
                raise ValueError(
                    "Stored CUA binding does not match the actual ADK context"
                )
            sid = binding.get("session_id")
            if not isinstance(sid, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,200}", sid
            ):
                raise ValueError("Invalid stored CUA SessionId")
            route["session_id"] = sid
        return {_META_KEY: route}

    async def get_tools(self, readonly_context=None):
        invocation = getattr(readonly_context, "_invocation_context", None)
        try:
            meta = self._metadata(readonly_context)
        except Exception:
            if invocation is not None:
                self._remember_discovery_failure(invocation)
            raise
        try:
            lock_key = (
                readonly_context.session.app_name,
                meta[_META_KEY]["user_session_id"],
            )
            lock = self._prepare_locks.setdefault(lock_key, asyncio.Lock())
            async with lock:
                meta = self._metadata(readonly_context)
                cached = self._catalogs.get(id(invocation))
                if cached and cached[0]() is invocation:
                    if (
                        cached[1][_META_KEY]["user_session_id"]
                        != meta[_META_KEY]["user_session_id"]
                    ):
                        raise ValueError("CUA session changed during invocation")
                    # A successful action may have added the first binding.
                    result = cached[2]
                else:
                    if id(invocation) in self._discovery_failures:
                        raise RuntimeError(
                            "CUA preparation previously failed in this invocation"
                        )
                    session = await asyncio.wait_for(self._manager.create_session(), 30)
                    # Only tools/list: never ensure or create in discovery.
                    result = await asyncio.wait_for(
                        session.list_tools(
                            params=types.PaginatedRequestParams(_meta=meta)
                        ),
                        self.timeout,
                    )
                    contract = (result.meta or {}).get(_META_KEY, {})
                    if contract.get("discovery_mode") != "template-fixed-v1":
                        raise RuntimeError(
                            "CUA MCP must support template-fixed-v1 discovery; refresh the wheel"
                        )
                    binding = self._response_binding(result, meta)
                    if (
                        binding is not None
                        and readonly_context.state.get(
                            self.binding_state_key(readonly_context)
                        )
                        != binding
                    ):
                        await invocation.session_service.append_event(
                            session=invocation.session,
                            event=Event(
                                invocation_id=invocation.invocation_id,
                                author=readonly_context.agent_name,
                                branch=invocation.branch,
                                actions=EventActions(
                                    state_delta={
                                        self.binding_state_key(
                                            readonly_context
                                        ): binding
                                    }
                                ),
                            ),
                        )
                        if (
                            readonly_context.state.get(
                                self.binding_state_key(readonly_context)
                            )
                            != binding
                        ):
                            raise RuntimeError("CUA binding was not persisted")
                    meta = self._metadata(readonly_context)
                    if result.nextCursor:
                        raise RuntimeError("Unexpected pagination in CUA catalog")
                    identity = id(invocation)
                    self._catalogs[identity] = (
                        weakref.ref(
                            invocation, lambda ref: self._catalogs.pop(identity, None)
                        ),
                        meta,
                        result,
                    )
        except asyncio.CancelledError:
            if invocation is not None:
                self._remember_discovery_failure(invocation)
            raise
        except Exception:
            if invocation is not None:
                self._remember_discovery_failure(invocation)
            raise RuntimeError(
                "CUA tool discovery failed; discovery does not create instances. "
                "Check template permissions and install a compatible template-fixed-v1 "
                "MCP wheel."
            ) from None
        if result.nextCursor:
            if invocation is not None:
                self._remember_discovery_failure(invocation)
            raise RuntimeError("Unexpected pagination in the CUA tool catalog")
        if invocation is not None:
            self._discovery_failures.pop(id(invocation), None)
        tools = [_ComputerTool(definition, self) for definition in result.tools]
        # Always keep the bootstrap entry even when a desktop allowlist is supplied.
        selected = [
            tool
            for tool in tools
            if tool.name == "ensure_sandbox"
            or self._is_tool_selected(tool, readonly_context)
        ]
        batch_available = any(t.name == "cua_actions_batch" for t in selected)
        for tool in selected:
            tool._batch_available = batch_available
        # Fixed means fixed across turns and process restarts, not just inside
        # one invocation. Persist a digest, never credentials or model state.
        key = "veadk_cua_catalog_" + self.binding_state_key(readonly_context)
        signature = hashlib.sha256(
            json.dumps(
                [
                    t._get_declaration().model_dump(mode="json", exclude_none=True)
                    for t in selected
                ],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        old = readonly_context.state.get(key)
        if old is not None and old != signature:
            self._remember_discovery_failure(invocation)
            raise RuntimeError("CUA catalog changed; start a new conversation/session")
        if old is None:
            await invocation.session_service.append_event(
                session=invocation.session,
                event=Event(
                    invocation_id=invocation.invocation_id,
                    author=readonly_context.agent_name,
                    branch=invocation.branch,
                    actions=EventActions(state_delta={key: signature}),
                ),
            )
        return selected

    @staticmethod
    def _response_binding(response, meta):
        contract = (response.meta or {}).get(_META_KEY, {})
        binding = contract.get("binding")
        if binding is None:
            return None
        expected = meta[_META_KEY]
        if (
            not isinstance(binding, dict)
            or set(binding) != {"user_session_id", "session_id"}
            or binding.get("user_session_id") != expected["user_session_id"]
            or not isinstance(binding.get("session_id"), str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", binding["session_id"])
            or (
                expected.get("session_id")
                and binding["session_id"] != expected["session_id"]
            )
        ):
            raise ValueError("CUA MCP returned an inconsistent sandbox binding")
        return dict(binding)

    def _remember_discovery_failure(self, invocation):
        identity = id(invocation)
        self._discovery_failures[identity] = weakref.ref(
            invocation, lambda ref: self._discovery_failures.pop(identity, None)
        )

    async def process_llm_request(self, *, tool_context, llm_request):
        # ADK catches get_tools failures and substitutes []; stop the model rather
        # than silently continuing without the requested CUA capability.
        if id(tool_context._invocation_context) in self._discovery_failures:
            raise RuntimeError("CUA tool discovery failed; model invocation aborted")
        # Adapt only Ark requests; other models retain their native tool media.
        from veadk.models.ark_llm import ArkLlm

        if isinstance(tool_context._invocation_context.agent.canonical_model, ArkLlm):
            from veadk.tools.computer_use.media import lift_screenshots

            # Adapt only images already in the request; history and cache
            # continuation remain owned by ADK and the original Ark adapter.
            lift_screenshots(llm_request)

    async def close(self):
        await self._manager.close()
        self._prepare_locks.clear()
        self._catalogs.clear()
        self._discovery_failures.clear()


def create_computer_use_toolset(
    *,
    connection_params: StdioServerParameters | None = None,
    tool_id: str | None = None,
    region: str | None = None,
    tool_filter: list[str] | None = None,
) -> ComputerUseToolset:
    """Launch the configured CUA MCP wheel with uvx on first use.

    The independent server is maintained in the cua-sandbox repository. When
    using the default uvx launcher, set ``CUA_MCP_WHEEL_URL`` to a trusted,
    explicitly versioned wheel URL in deployment configuration. Alternatively,
    pass ``connection_params`` for a preinstalled/offline command.
    Runtime must provide uvx; import does not download or create cloud resources.
    Discovery reads template/instance capabilities without creating a sandbox.
    The first valid desktop action (or explicit ensure) creates/reuses an instance;
    pure chat does not create a billable sandbox through this Toolset.
    """
    tool_id = (
        tool_id
        or os.getenv("AGENTKIT_TOOL_ID_CUA")
        or os.getenv("AGENTKIT_TOOL_ID", "")
    )
    region = region or os.getenv("AGENTKIT_TOOL_REGION", "cn-beijing")
    if connection_params is None:
        wheel_url = os.getenv("CUA_MCP_WHEEL_URL", "").strip()
        if not wheel_url:
            raise ValueError(
                "CUA_MCP_WHEEL_URL must be set to an explicitly versioned CUA MCP "
                "wheel URL when using the default uvx launcher; alternatively, "
                "pass connection_params for a preinstalled or local server."
            )
        connection_params = StdioServerParameters(
            command="uvx",
            args=[
                "--from",
                wheel_url,
                "agentkit-cua-mcp",
                "--transport",
                "stdio",
            ],
            env={name: os.environ[name] for name in _FORWARD_ENV if name in os.environ},
        )
    return ComputerUseToolset(
        connection_params=connection_params,
        tool_id=tool_id,
        region=region,
        tool_filter=tool_filter,
    )
