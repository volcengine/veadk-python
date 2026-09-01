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

import asyncio

import pytest

from frontend.server.studio_tools.branch_compare import (
    BranchCompareService,
    _PacedDeltaReporter,
)
from frontend.server.studio_tools.registry import (
    StudioToolExecutionContext,
    StudioToolExecutionError,
    build_studio_tool_registry,
)


def _context(progress: list[dict[str, object]]) -> StudioToolExecutionContext:
    async def report(event: dict[str, object]) -> None:
        progress.append(event)

    return StudioToolExecutionContext(
        runtime_id="runtime-1",
        app_name="agent-1",
        user_id="user-1",
        session_id="session-1",
        run_id="run-1",
        scope_id="scope-1",
        catalog_revision="revision-1",
        tool_request_id="tool-call-1",
        report_progress=report,
    )


def _arguments() -> dict[str, object]:
    return {
        "prompt": "设计一个创建 Agent 的方案",
        "branches": [
            {"label": "稳妥", "instruction": "优先兼容现有流程"},
            {"label": "创新", "instruction": "强调对话式创建"},
        ],
    }


@pytest.mark.asyncio
async def test_paced_delta_reporter_turns_a_burst_into_renderable_chunks() -> None:
    emitted: list[str] = []
    sleeps: list[float] = []

    async def report(delta: str) -> None:
        emitted.append(delta)

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    reporter = _PacedDeltaReporter(
        report,
        chunk_chars=4,
        interval_seconds=0.05,
        sleep=sleep,
    )
    await reporter.add("一二三四五")
    await reporter.add("六七八九")
    await reporter.finish()
    await reporter.finish()

    assert emitted == ["一二三四", "五六七八", "九"]
    assert sleeps == [0.05, 0.05]


def test_branch_compare_is_part_of_the_dynamic_studio_catalog() -> None:
    registry = build_studio_tool_registry()
    manifest = next(
        item for item in registry.manifests() if item["name"] == "branch_compare"
    )

    assert manifest["input_schema"]["properties"]["branches"]["minItems"] == 2
    assert manifest["input_schema"]["properties"]["branches"]["maxItems"] == 2
    assert (
        manifest["input_schema"]["properties"]["branches"]["items"]["properties"][
            "label"
        ]["maxLength"]
        == 10
    )


@pytest.mark.asyncio
async def test_branch_compare_streams_both_branches_concurrently() -> None:
    both_started = asyncio.Event()
    started: set[str] = set()

    async def generate(prompt: str, instruction: str, report) -> str:  # noqa: ANN001
        assert prompt == "设计一个创建 Agent 的方案"
        started.add(instruction)
        if len(started) == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=1)
        text = "保留工作台" if "兼容" in instruction else "边聊边预览"
        await report(text[:2])
        await report(text[2:])
        return text

    progress: list[dict[str, object]] = []
    result = await BranchCompareService(generate).execute(
        _arguments(), _context(progress)
    )

    assert [item["content"] for item in result["branches"]] == [
        "保留工作台",
        "边聊边预览",
    ]
    assert {item["branchIndex"] for item in progress} == {0, 1}
    assert [item["status"] for item in progress].count("completed") == 2


@pytest.mark.asyncio
async def test_branch_compare_keeps_the_other_branch_when_one_fails() -> None:
    async def generate(prompt: str, instruction: str, report) -> str:  # noqa: ANN001
        del prompt
        if "兼容" in instruction:
            raise RuntimeError("upstream unavailable")
        await report("可用结果")
        return "可用结果"

    progress: list[dict[str, object]] = []
    result = await BranchCompareService(generate).execute(
        _arguments(), _context(progress)
    )

    assert result["branches"][0]["status"] == "failed"
    assert result["branches"][1] == {
        "label": "创新",
        "content": "可用结果",
        "status": "completed",
    }
    assert any(item["status"] == "failed" for item in progress)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    [
        {"prompt": "x", "branches": [{"label": "A", "instruction": "x"}]},
        {
            "prompt": "x",
            "branches": [
                {"label": "超过十个字符的方向标签", "instruction": "x"},
                {"label": "B", "instruction": "y"},
            ],
        },
        {
            "prompt": "",
            "branches": [
                {"label": "A", "instruction": "x"},
                {"label": "B", "instruction": "y"},
            ],
        },
        {
            "prompt": "   ",
            "branches": [
                {"label": "A", "instruction": "x"},
                {"label": "B", "instruction": "y"},
            ],
        },
        {
            "prompt": "x",
            "branches": [
                {"label": "   ", "instruction": "x"},
                {"label": "B", "instruction": "y"},
            ],
        },
    ],
)
async def test_branch_compare_rejects_invalid_arguments(
    arguments: dict[str, object],
) -> None:
    registry = build_studio_tool_registry()

    with pytest.raises(StudioToolExecutionError, match="Invalid arguments"):
        await registry.execute(
            name="branch_compare",
            executor_revision="branch-compare-v1",
            arguments=arguments,
            context=_context([]),
        )
