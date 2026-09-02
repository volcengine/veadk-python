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

from __future__ import annotations

from typing import Any

import pytest

from frontend.server.studio_tools.local import build_local_studio_tools
from frontend.server.studio_tools.registry import (
    StudioTool,
    StudioToolExecutionContext,
    StudioToolRegistry,
    StudioToolRuntimeError,
)


def _context(revision: str) -> StudioToolExecutionContext:
    return StudioToolExecutionContext(
        runtime_id="local",
        app_name="agent",
        user_id="user-1",
        session_id="session-1",
        run_id="run-1",
        scope_id="scope-1",
        catalog_revision=revision,
    )


@pytest.mark.asyncio
async def test_local_tools_execute_catalog_and_forward_progress() -> None:
    progress: list[dict[str, Any]] = []
    contexts: list[StudioToolExecutionContext] = []

    async def execute(
        arguments: dict[str, Any],
        context: StudioToolExecutionContext,
    ) -> dict[str, Any]:
        contexts.append(context)
        assert context.report_progress is not None
        await context.report_progress(
            {"kind": "codex", "event": {"kind": "thinking", "text": "分析"}}
        )
        return {"ok": True, "task": arguments["task"]}

    registry = StudioToolRegistry()
    registry.register(
        StudioTool(
            name="delegate_to_codex_sandbox",
            description="Delegate to Codex.",
            input_schema={
                "type": "object",
                "properties": {"task": {"type": "string"}},
                "required": ["task"],
                "additionalProperties": False,
            },
            executor=execute,
            executor_revision="v1",
            requires_context=True,
        )
    )
    catalog = registry.snapshot(["delegate_to_codex_sandbox"])

    async def report_progress(event: dict[str, Any]) -> None:
        progress.append(event)

    [tool] = build_local_studio_tools(
        catalog=catalog,
        context=_context(catalog.revision),
        report_progress=report_progress,
    )

    result = await tool.run_async(
        args={"task": "review"},
        tool_context=type("ToolContext", (), {"function_call_id": "call-1"})(),
    )

    assert result == {"ok": True, "task": "review"}
    assert contexts[0].tool_request_id == "call-1"
    assert progress == [
        {
            "toolName": "delegate_to_codex_sandbox",
            "requestId": "call-1",
            "kind": "codex",
            "event": {"kind": "thinking", "text": "分析"},
        }
    ]


@pytest.mark.asyncio
async def test_local_tool_returns_runtime_error_content_to_agent() -> None:
    async def execute(
        arguments: dict[str, Any],
        context: StudioToolExecutionContext,
    ) -> dict[str, Any]:
        del arguments, context
        raise StudioToolRuntimeError(
            "Codex disconnected.",
            content={"codex_activity": {"events": [{"status": "failed"}]}},
        )

    registry = StudioToolRegistry()
    registry.register(
        StudioTool(
            name="delegate_to_codex_sandbox",
            description="Delegate to Codex.",
            input_schema={"type": "object", "additionalProperties": False},
            executor=execute,
            executor_revision="v1",
            requires_context=True,
        )
    )
    catalog = registry.snapshot(["delegate_to_codex_sandbox"])

    async def report_progress(progress: dict[str, Any]) -> None:
        del progress

    [tool] = build_local_studio_tools(
        catalog=catalog,
        context=_context(catalog.revision),
        report_progress=report_progress,
    )

    result = await tool.run_async(
        args={},
        tool_context=type("ToolContext", (), {"function_call_id": "call-1"})(),
    )

    assert result == {
        "status": "runtime_error",
        "error": "Codex disconnected.",
        "codex_activity": {"events": [{"status": "failed"}]},
    }
