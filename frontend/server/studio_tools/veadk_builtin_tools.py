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

"""BFF adapters for the canonical VeADK built-in tool implementations."""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import quote

from frontend.server.studio_tools.builtin_declarations import (
    BUILTIN_TOOL_DECLARATIONS,
)
from frontend.server.studio_tools.registry import (
    StudioTool,
    StudioToolExecutionContext,
    StudioToolRegistry,
)

if TYPE_CHECKING:
    from veadk.multimodal.service import MediaService


def FunctionTool(*args: Any, **kwargs: Any) -> Any:  # noqa: N802
    """Construct ADK's adapter only when a built-in tool is first invoked."""

    from google.adk.tools.function_tool import FunctionTool as _FunctionTool

    return _FunctionTool(*args, **kwargs)


def get_builtin_tool(name: str) -> Any:
    """Resolve a canonical VeADK callable only for an actual tool call."""

    from veadk.tools import get_builtin_tool as _get_builtin_tool

    return _get_builtin_tool(name)


def list_builtin_tools() -> list[str]:
    """Return the declaration-locked built-in catalog without loading VeADK tools."""

    return sorted(BUILTIN_TOOL_DECLARATIONS)


_DISPLAY_NAMES = {
    "coding": "智能编程",
    "get_city_weather": "城市天气查询",
    "get_location_weather": "位置天气查询",
    "image_edit": "图片编辑",
    "image_generate": "图片生成",
    "link_reader": "链接内容读取",
    "parallel_web_search": "并行网页搜索",
    "ppt_generate": "PPT 生成",
    "run_code": "代码运行",
    "text_to_speech": "文本转语音",
    "vesearch": "联网搜索",
    "video_generate": "视频生成",
    "video_task_query": "视频任务查询",
    "web_fetch": "网页内容获取",
    "web_search": "网页搜索",
}

_LONG_RUNNING_TOOLS = {
    "coding",
    "image_edit",
    "image_generate",
    "ppt_generate",
    "run_code",
    "text_to_speech",
    "video_generate",
}

_IDEMPOTENT_TOOLS = {
    "get_city_weather",
    "get_location_weather",
    "link_reader",
    "parallel_web_search",
    "vesearch",
    "video_task_query",
    "web_fetch",
    "web_search",
}

_DEFERRED_BUILTIN_DECLARATIONS = BUILTIN_TOOL_DECLARATIONS


@dataclass
class _BuiltinExecutionHost:
    """Own the BFF-local ADK context needed by existing tool callables."""

    session_service: Any | None = None
    artifact_service: Any | None = None
    media_service: MediaService | None = None
    agent: Any | None = None
    states: dict[str, dict[str, Any]] = field(default_factory=dict)
    locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    initialization_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def _ensure_runtime(self) -> None:
        if self.session_service is not None:
            return
        async with self.initialization_lock:
            if self.session_service is not None:
                return
            from google.adk.agents import Agent
            from google.adk.artifacts.in_memory_artifact_service import (
                InMemoryArtifactService,
            )
            from google.adk.sessions import InMemorySessionService

            self.session_service = InMemorySessionService()
            self.artifact_service = InMemoryArtifactService()
            self.agent = Agent(name="studio_bff_agent")

    async def execute(
        self,
        function_tool: Any,
        arguments: dict[str, Any],
        context: StudioToolExecutionContext,
    ) -> Any:
        await self._ensure_runtime()
        from google.adk.agents.invocation_context import InvocationContext
        from google.adk.sessions import Session
        from google.adk.tools.tool_context import ToolContext

        session_service = self.session_service
        artifact_service = self.artifact_service
        agent = self.agent
        if session_service is None or artifact_service is None or agent is None:
            raise RuntimeError("Studio built-in execution runtime is unavailable")

        lock = self.locks.setdefault(context.scope_id, asyncio.Lock())
        async with lock:
            session = Session(
                id=context.session_id,
                app_name=context.app_name,
                user_id=context.user_id,
                state=dict(self.states.get(context.scope_id, {})),
            )
            invocation_context = InvocationContext(
                artifact_service=artifact_service,
                session_service=session_service,
                invocation_id=context.run_id,
                agent=agent,
                session=session,
            )
            tool_context = ToolContext(
                invocation_context,
                function_call_id=f"studio:{function_tool.name}:{context.run_id}",
                run_id=context.run_id,
            )
            try:
                result = await function_tool.run_async(
                    args=arguments,
                    tool_context=tool_context,
                )
                artifacts = await self._publish_artifacts(tool_context, context)
                if not artifacts:
                    return result
                if isinstance(result, dict):
                    return {**result, "studio_artifacts": artifacts}
                return {"result": result, "studio_artifacts": artifacts}
            finally:
                self.states[context.scope_id] = tool_context.state.to_dict()

    async def _publish_artifacts(
        self,
        tool_context: Any,
        context: StudioToolExecutionContext,
    ) -> list[dict[str, Any]]:
        """Make ADK artifacts produced in BFF execution available to Studio."""

        if self.media_service is None:
            return []
        artifact_service = self.artifact_service
        if artifact_service is None:
            raise RuntimeError("Studio built-in artifact runtime is unavailable")
        published: list[dict[str, Any]] = []
        for filename, version in tool_context.actions.artifact_delta.items():
            artifact = await artifact_service.load_artifact(
                app_name=context.app_name,
                user_id=context.user_id,
                session_id=context.session_id,
                filename=filename,
                version=version,
            )
            if artifact is None or artifact.inline_data is None:
                continue
            mime_type = artifact.inline_data.mime_type
            data = artifact.inline_data.data
            if not mime_type or data is None:
                continue
            record = await self.media_service.save_bytes(
                app_name=context.app_name,
                user_id=context.user_id,
                session_id=context.session_id,
                file_name=filename,
                mime_type=mime_type,
                data=data,
                origin="model",
            )
            ref = record.ref
            encoded = "/".join(
                quote(value, safe="")
                for value in (
                    ref.app_name,
                    ref.user_id,
                    ref.session_id,
                    ref.media_id,
                )
            )
            published.append(
                {
                    **record.to_api_dict(),
                    "contentUrl": f"/web/media/{encoded}/content",
                    "artifactVersion": version,
                }
            )
        return published


def _schema(function_tool: Any) -> tuple[str, dict[str, Any]]:
    declaration = function_tool._get_declaration()
    if declaration is None:
        raise ValueError(f"Built-in tool has no declaration: {function_tool.name}")
    schema: dict[str, Any] = dict(
        declaration.parameters_json_schema or {"type": "object"}
    )
    schema.setdefault("additionalProperties", False)
    description = (declaration.description or function_tool.name).strip()[:4096]
    return description, schema


def _deferred_schema(name: str) -> tuple[str, dict[str, Any]]:
    description, schema = _DEFERRED_BUILTIN_DECLARATIONS[name]
    copied_schema = copy.deepcopy(schema)
    copied_schema.setdefault("additionalProperties", False)
    return description, copied_schema


def _normalize_schema_value(value: Any) -> Any:
    """Normalize the nullable schema form that varies across Pydantic runtimes."""

    if isinstance(value, list):
        return [_normalize_schema_value(item) for item in value]
    if not isinstance(value, dict):
        return value

    normalized = {key: _normalize_schema_value(item) for key, item in value.items()}
    any_of = normalized.get("anyOf")
    if (
        not isinstance(any_of, list)
        or len(any_of) != 2
        or "default" not in normalized
        or normalized["default"] is not None
    ):
        return normalized

    null_branches = [branch for branch in any_of if branch == {"type": "null"}]
    value_branches = [branch for branch in any_of if branch != {"type": "null"}]
    if (
        len(null_branches) != 1
        or len(value_branches) != 1
        or not isinstance(value_branches[0], dict)
    ):
        return normalized

    merged = {key: item for key, item in normalized.items() if key != "anyOf"}
    for key, item in value_branches[0].items():
        if key in merged and merged[key] != item:
            return normalized
        merged[key] = item
    return merged


def _schemas_match(
    left: tuple[str, dict[str, Any]],
    right: tuple[str, dict[str, Any]],
) -> bool:
    """Compare deferred declarations across supported Python/Pydantic forms."""

    return left[0] == right[0] and _normalize_schema_value(
        left[1]
    ) == _normalize_schema_value(right[1])


def register_veadk_builtin_tools(
    registry: StudioToolRegistry,
    *,
    media_service: MediaService | None = None,
) -> None:
    """Expose the existing VeADK built-ins through the Studio-owned channel."""

    host = _BuiltinExecutionHost(media_service=media_service)
    resolved_tools: dict[str, Any] = {}
    for name in list_builtin_tools():
        if name in _DEFERRED_BUILTIN_DECLARATIONS:
            description, input_schema = _deferred_schema(name)
        else:
            function_tool = FunctionTool(
                cast(Callable[..., Any], get_builtin_tool(name))
            )
            resolved_tools[name] = function_tool
            description, input_schema = _schema(function_tool)

        async def execute(
            arguments: dict[str, Any],
            context: StudioToolExecutionContext,
            *,
            current_name: str = name,
        ) -> Any:
            current_tool = resolved_tools.get(current_name)
            if current_tool is None:
                current_tool = FunctionTool(
                    cast(Callable[..., Any], get_builtin_tool(current_name))
                )
                if not _schemas_match(
                    _schema(current_tool), _deferred_schema(current_name)
                ):
                    raise RuntimeError(
                        f"Deferred built-in declaration changed: {current_name}"
                    )
                resolved_tools[current_name] = current_tool
            return await host.execute(current_tool, arguments, context)

        registry.register(
            StudioTool(
                name=name,
                display_name=_DISPLAY_NAMES.get(name, name),
                description=description,
                input_schema=input_schema,
                executor=execute,
                executor_revision="veadk-builtin-v1",
                timeout_ms=120_000,
                idempotent=name in _IDEMPOTENT_TOOLS,
                risk_level="medium" if name in _LONG_RUNNING_TOOLS else "low",
                requires_context=True,
            )
        )


__all__ = ["register_veadk_builtin_tools"]
