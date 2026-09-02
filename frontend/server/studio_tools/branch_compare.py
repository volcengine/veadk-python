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

"""Studio-owned parallel branch generation tool."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import InMemoryRunner
from google.genai import types

from frontend.server.studio_tools.registry import (
    StudioTool,
    StudioToolExecutionContext,
    StudioToolExecutionError,
    StudioToolRegistry,
)
from veadk import Agent

BRANCH_COMPARE_TOOL_NAME = "branch_compare"
DEFAULT_BRANCH_MODEL = "doubao-seed-2-0-lite-260428"
BRANCH_STREAM_CHUNK_CHARS = 16
BRANCH_STREAM_INTERVAL_SECONDS = 0.05
BranchDeltaReporter = Callable[[str], Awaitable[None]]
BranchGenerator = Callable[[str, str, BranchDeltaReporter], Awaitable[str]]


class _PacedDeltaReporter:
    """Relay bursty model tokens as paintable, bounded progress chunks."""

    _STOP = object()

    def __init__(
        self,
        report_delta: BranchDeltaReporter,
        *,
        chunk_chars: int = BRANCH_STREAM_CHUNK_CHARS,
        interval_seconds: float = BRANCH_STREAM_INTERVAL_SECONDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._report_delta = report_delta
        self._chunk_chars = chunk_chars
        self._interval_seconds = interval_seconds
        self._sleep = sleep
        self._queue: asyncio.Queue[str | object] = asyncio.Queue()
        self._task = asyncio.create_task(self._run())
        self._finished = False

    async def add(self, delta: str) -> None:
        if not delta:
            return
        if self._task.done():
            self._task.result()
        await self._queue.put(delta)

    async def finish(self) -> None:
        if not self._finished:
            self._finished = True
            await self._queue.put(self._STOP)
        await self._task

    def cancel(self) -> None:
        self._task.cancel()

    async def _run(self) -> None:
        buffered = ""
        stopped = False
        while not stopped or buffered:
            if not buffered:
                item = await self._queue.get()
                if item is self._STOP:
                    stopped = True
                    continue
                buffered = str(item)

            while len(buffered) < self._chunk_chars and not self._queue.empty():
                item = self._queue.get_nowait()
                if item is self._STOP:
                    stopped = True
                    break
                buffered += str(item)

            chunk = buffered[: self._chunk_chars]
            buffered = buffered[self._chunk_chars :]
            await self._report_delta(chunk)
            if not stopped or buffered:
                await self._sleep(self._interval_seconds)


BRANCH_COMPARE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "prompt": {
            "type": "string",
            "minLength": 1,
            "maxLength": 12_000,
            "pattern": r"\S",
            "description": "两个方向共同回答的任务或问题。",
        },
        "branches": {
            "type": "array",
            "minItems": 2,
            "maxItems": 2,
            "items": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 10,
                        "pattern": r"\S",
                        "description": "10 字以内的方向名称。",
                    },
                    "instruction": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 4_000,
                        "pattern": r"\S",
                        "description": "该方向独有的生成要求。",
                    },
                },
                "required": ["label", "instruction"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["prompt", "branches"],
    "additionalProperties": False,
}


async def _generate_with_model(
    prompt: str,
    instruction: str,
    report_delta: BranchDeltaReporter,
) -> str:
    model_name = os.getenv("VEADK_STUDIO_BRANCH_MODEL", DEFAULT_BRANCH_MODEL).strip()
    agent = Agent(
        name=f"studio_branch_{uuid4().hex[:12]}",
        description="Generate one focused comparison branch for AgentKit Studio.",
        instruction=(
            "你正在生成一个对比方案中的单一方向。严格遵循该方向要求，直接输出可独立阅读的"
            "Markdown 正文。不要提及另一个方向，不要添加方向标题、状态说明或选择提示。\n\n"
            f"方向要求：{instruction}"
        ),
        model_name=model_name,
        enable_responses=True,
        enable_responses_cache=False,
        model_extra_config={"extra_body": {"thinking": {"type": "disabled"}}},
    )
    runner = InMemoryRunner(agent=agent, app_name=agent.name)
    user_id = "studio-branch"
    session_id = f"branch-{uuid4().hex}"
    await runner.session_service.create_session(
        app_name=runner.app_name,
        user_id=user_id,
        session_id=session_id,
    )

    streamed_parts: list[str] = []
    final_text = ""
    paced_reporter = _PacedDeltaReporter(report_delta)
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.UserContent(parts=[types.Part(text=prompt)]),
            run_config=RunConfig(streaming_mode=StreamingMode.SSE, max_llm_calls=1),
        ):
            for part in (
                event.content.parts if event.content and event.content.parts else []
            ):
                text = part.text or ""
                if not text or part.thought:
                    continue
                if event.partial:
                    streamed_parts.append(text)
                    await paced_reporter.add(text)
                else:
                    final_text = text

        if not final_text:
            final_text = "".join(streamed_parts)
        elif not streamed_parts:
            await paced_reporter.add(final_text)
        await paced_reporter.finish()
        return final_text
    except asyncio.CancelledError:
        paced_reporter.cancel()
        raise
    except Exception:
        await paced_reporter.finish()
        raise


class BranchCompareService:
    def __init__(self, generator: BranchGenerator = _generate_with_model) -> None:
        self._generator = generator

    async def execute(
        self,
        arguments: dict[str, Any],
        context: StudioToolExecutionContext,
    ) -> dict[str, Any]:
        prompt = str(arguments["prompt"]).strip()
        if not prompt:
            raise StudioToolExecutionError("分支对比的 prompt 不能为空。")
        branches = arguments["branches"]

        async def run_branch(index: int, branch: dict[str, Any]) -> dict[str, Any]:
            label = str(branch["label"]).strip()
            instruction = str(branch["instruction"]).strip()
            if not label or not instruction:
                raise StudioToolExecutionError("分支的 label 和 instruction 不能为空。")

            async def report_delta(delta: str) -> None:
                if context.report_progress is None or not delta:
                    return
                await context.report_progress(
                    {
                        "branchIndex": index,
                        "label": label,
                        "delta": delta,
                        "status": "running",
                    }
                )

            if context.report_progress is not None:
                await context.report_progress(
                    {
                        "branchIndex": index,
                        "label": label,
                        "delta": "",
                        "status": "running",
                    }
                )
            try:
                content = await self._generator(prompt, instruction, report_delta)
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - isolate one branch failure
                if context.report_progress is not None:
                    await context.report_progress(
                        {
                            "branchIndex": index,
                            "label": label,
                            "delta": "",
                            "status": "failed",
                            "error": "该方向生成失败，请重试。",
                        }
                    )
                return {
                    "label": label,
                    "content": "",
                    "status": "failed",
                    "error": "该方向生成失败，请重试。",
                    "diagnostics": {"type": type(error).__name__},
                }

            if context.report_progress is not None:
                await context.report_progress(
                    {
                        "branchIndex": index,
                        "label": label,
                        "delta": "",
                        "status": "completed",
                    }
                )
            return {"label": label, "content": content, "status": "completed"}

        results = await asyncio.gather(
            *(run_branch(index, branch) for index, branch in enumerate(branches))
        )
        return {"branches": list(results)}


def register_branch_compare_tool(registry: StudioToolRegistry) -> None:
    service = BranchCompareService()
    registry.register(
        StudioTool(
            name=BRANCH_COMPARE_TOOL_NAME,
            display_name="分支对比",
            description=(
                "并行生成两个可直接比较的方向。用户明确要求两种风格、两套方案或两个创意方向时"
                "调用。branches 必须恰好包含两个方向，每个 label 不超过 10 个字符。"
            ),
            input_schema=BRANCH_COMPARE_INPUT_SCHEMA,
            executor=service.execute,
            executor_revision="branch-compare-v1",
            timeout_ms=120_000,
            risk_level="low",
            requires_context=True,
        )
    )


__all__ = [
    "BRANCH_COMPARE_INPUT_SCHEMA",
    "BRANCH_COMPARE_TOOL_NAME",
    "BranchCompareService",
    "register_branch_compare_tool",
]
