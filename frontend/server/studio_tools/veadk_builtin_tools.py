# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""BFF adapters for the canonical VeADK built-in tool implementations."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from google.adk.agents import Agent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.sessions import InMemorySessionService, Session
from google.adk.tools import FunctionTool, ToolContext

from frontend.server.studio_tools.registry import (
    StudioTool,
    StudioToolExecutionContext,
    StudioToolRegistry,
)
from veadk.multimodal.service import MediaService
from veadk.tools import get_builtin_tool, list_builtin_tools


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


@dataclass
class _BuiltinExecutionHost:
    """Own the BFF-local ADK context needed by existing tool callables."""

    session_service: InMemorySessionService = field(
        default_factory=InMemorySessionService
    )
    artifact_service: InMemoryArtifactService = field(
        default_factory=InMemoryArtifactService
    )
    media_service: MediaService | None = None
    agent: Agent = field(default_factory=lambda: Agent(name="studio_bff_agent"))
    states: dict[str, dict[str, Any]] = field(default_factory=dict)
    locks: dict[str, asyncio.Lock] = field(default_factory=dict)

    async def execute(
        self,
        function_tool: FunctionTool,
        arguments: dict[str, Any],
        context: StudioToolExecutionContext,
    ) -> Any:
        lock = self.locks.setdefault(context.scope_id, asyncio.Lock())
        async with lock:
            session = Session(
                id=context.session_id,
                appName=context.app_name,
                userId=context.user_id,
                state=dict(self.states.get(context.scope_id, {})),
            )
            invocation_context = InvocationContext(
                artifact_service=self.artifact_service,
                session_service=self.session_service,
                invocation_id=context.run_id,
                agent=self.agent,
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
        tool_context: ToolContext,
        context: StudioToolExecutionContext,
    ) -> list[dict[str, Any]]:
        """Make ADK artifacts produced in BFF execution available to Studio."""

        if self.media_service is None:
            return []
        published: list[dict[str, Any]] = []
        for filename, version in tool_context.actions.artifact_delta.items():
            artifact = await self.artifact_service.load_artifact(
                app_name=context.app_name,
                user_id=context.user_id,
                session_id=context.session_id,
                filename=filename,
                version=version,
            )
            if artifact is None or artifact.inline_data is None:
                continue
            record = await self.media_service.save_bytes(
                app_name=context.app_name,
                user_id=context.user_id,
                session_id=context.session_id,
                file_name=filename,
                mime_type=artifact.inline_data.mime_type,
                data=artifact.inline_data.data,
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


def _schema(function_tool: FunctionTool) -> tuple[str, dict[str, Any]]:
    declaration = function_tool._get_declaration()
    if declaration is None:
        raise ValueError(f"Built-in tool has no declaration: {function_tool.name}")
    schema = dict(declaration.parameters_json_schema or {"type": "object"})
    schema.setdefault("additionalProperties", False)
    description = (declaration.description or function_tool.name).strip()[:4096]
    return description, schema


def register_veadk_builtin_tools(
    registry: StudioToolRegistry,
    *,
    media_service: MediaService | None = None,
) -> None:
    """Expose the existing VeADK built-ins through the Studio-owned channel."""

    host = _BuiltinExecutionHost(media_service=media_service)
    for name in list_builtin_tools():
        function_tool = FunctionTool(get_builtin_tool(name))
        description, input_schema = _schema(function_tool)

        async def execute(
            arguments: dict[str, Any],
            context: StudioToolExecutionContext,
            *,
            current_tool: FunctionTool = function_tool,
        ) -> Any:
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
