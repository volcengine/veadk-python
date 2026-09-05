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

"""Run Studio BFF tools directly inside a local ADK invocation."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import replace
from typing import Any
from uuid import uuid4

from google.adk.tools.base_tool import BaseTool

from frontend.server.studio_tools.registry import (
    StudioToolCatalogSnapshot,
    StudioToolExecutionContext,
    StudioToolExecutionError,
    StudioToolRuntimeError,
)
from veadk.integrations.agentkit.studio_channel import (
    StudioExternalToolset,
    StudioRemoteTool,
    bind_studio_tools,
)
from veadk.integrations.agentkit.studio_channel.protocol import StudioToolManifest

logger = logging.getLogger(__name__)

ProgressReporter = Callable[[dict[str, Any]], Awaitable[None]]


class LocalStudioToolDispatcher:
    """Adapt a frozen BFF catalog to the Runtime's model-visible tools."""

    def __init__(
        self,
        *,
        catalog: StudioToolCatalogSnapshot,
        context: StudioToolExecutionContext,
        report_progress: ProgressReporter,
    ) -> None:
        self._catalog = catalog
        self._context = context
        self._report_progress = report_progress

    async def call_tool(
        self,
        *,
        run_id: str,
        scope_id: str,
        catalog_revision: str,
        manifest: StudioToolManifest,
        arguments: dict[str, Any],
        function_call_id: str = "",
    ) -> Any:
        """Execute one catalog tool with the same status contract as the channel."""

        if (
            run_id != self._context.run_id
            or scope_id != self._context.scope_id
            or catalog_revision != self._context.catalog_revision
        ):
            return {
                "status": "denied",
                "error": "Studio tool call context mismatch.",
            }

        request_id = function_call_id or uuid4().hex

        async def report(progress: dict[str, Any]) -> None:
            await self._report_progress(
                {
                    "toolName": manifest.name,
                    "requestId": request_id,
                    **progress,
                }
            )

        context = replace(
            self._context,
            tool_request_id=request_id,
            report_progress=report,
        )
        try:
            return await asyncio.wait_for(
                self._catalog.execute(
                    name=manifest.name,
                    executor_revision=manifest.executor_revision,
                    arguments=arguments,
                    context=context,
                ),
                timeout=manifest.timeout_ms / 1000,
            )
        except asyncio.TimeoutError:
            return {
                "status": "timeout",
                "error": (
                    "Codex Sandbox 长任务超过 30 分钟，已停止执行；"
                    "请确认当前状态后再决定是否重新提交。"
                    if manifest.name == "delegate_to_codex_sandbox"
                    else "Studio tool timed out."
                ),
            }
        except StudioToolRuntimeError as error:
            response = dict(error.content) if isinstance(error.content, dict) else {}
            response.update(status="runtime_error", error=str(error))
            return response
        except StudioToolExecutionError as error:
            return {"status": "denied", "error": str(error)}
        except Exception:  # noqa: BLE001 - local tool safety boundary
            logger.exception(
                "Local Studio tool execution failed tool=%s run_id=%s",
                manifest.name,
                run_id,
            )
            return {
                "status": "error",
                "error": "Studio BFF tool execution failed.",
            }


def build_local_studio_tools(
    *,
    catalog: StudioToolCatalogSnapshot,
    context: StudioToolExecutionContext,
    report_progress: ProgressReporter,
) -> tuple[BaseTool, ...]:
    """Build immutable model-visible wrappers for one local Agent run."""

    dispatcher = LocalStudioToolDispatcher(
        catalog=catalog,
        context=context,
        report_progress=report_progress,
    )
    return tuple(
        StudioRemoteTool(
            manifest=StudioToolManifest.model_validate(manifest),
            dispatcher=dispatcher,
            run_id=context.run_id,
            scope_id=context.scope_id,
            catalog_revision=context.catalog_revision,
        )
        for manifest in catalog.manifests()
    )


def ensure_local_studio_toolset(
    runner: Any,
    selected_names: Sequence[str],
) -> None:
    """Attach the run-scoped Studio toolset to a cached local ADK runner."""

    app = getattr(runner, "app", None)
    root_agent = getattr(app, "root_agent", None)
    tools = getattr(root_agent, "tools", None)
    if not isinstance(tools, list):
        raise StudioToolExecutionError(
            "The selected local Agent cannot accept Studio tools."
        )
    selected = set(selected_names)
    reserved = {
        str(getattr(tool, "name", "") or "")
        for tool in tools
        if not isinstance(tool, StudioExternalToolset)
    }
    conflicts = sorted(selected.intersection(reserved))
    if conflicts:
        raise StudioToolExecutionError(
            "Studio tool names conflict with local Agent tools: " + ", ".join(conflicts)
        )
    if not any(isinstance(tool, StudioExternalToolset) for tool in tools):
        tools.append(StudioExternalToolset())


def local_progress_sse_event(
    *,
    app_name: str,
    progress: dict[str, Any],
) -> bytes:
    """Encode local tool progress with the existing Studio SSE contract."""

    request_id = str(progress.get("requestId") or uuid4().hex)
    event = {
        "id": f"studio-tool-progress:{request_id}:{uuid4().hex}",
        "author": app_name,
        "partial": True,
        "content": {
            "role": "model",
            "parts": [
                {
                    "partMetadata": {
                        "veadkStudioToolProgress": progress,
                    }
                }
            ],
        },
    }
    return (
        "data: " + json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n\n"
    ).encode("utf-8")


async def stream_local_studio_response(
    source: AsyncIterator[bytes | str],
    *,
    tools: Sequence[BaseTool],
    progress_events: asyncio.Queue[bytes],
) -> AsyncIterator[bytes | str]:
    """Merge direct tool progress into the local ADK SSE response."""

    source_task: asyncio.Task[bytes | str] | None = None
    progress_task: asyncio.Task[bytes] | None = None
    iterator = source.__aiter__()
    try:
        with bind_studio_tools(tools):
            while True:
                if source_task is None:
                    source_task = asyncio.create_task(anext(iterator))
                if progress_task is None:
                    progress_task = asyncio.create_task(progress_events.get())
                done, _ = await asyncio.wait(
                    {source_task, progress_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if progress_task in done:
                    yield progress_task.result()
                    progress_task = None
                if source_task in done:
                    try:
                        chunk = source_task.result()
                    except StopAsyncIteration:
                        source_task = None
                        while not progress_events.empty():
                            yield progress_events.get_nowait()
                        return
                    source_task = None
                    yield chunk
    finally:
        for task in (source_task, progress_task):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (source_task, progress_task) if task is not None),
            return_exceptions=True,
        )
        aclose = getattr(iterator, "aclose", None)
        if callable(aclose):
            await aclose()


__all__ = [
    "LocalStudioToolDispatcher",
    "build_local_studio_tools",
    "ensure_local_studio_toolset",
    "local_progress_sse_event",
    "stream_local_studio_response",
]
