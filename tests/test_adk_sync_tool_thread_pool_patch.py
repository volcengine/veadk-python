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

import time

import pytest
from google.adk.agents import LlmAgent, RunConfig
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.run_config import ToolThreadPoolConfig
from google.adk.flows.llm_flows import functions
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.sessions.session import Session
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from veadk import Agent
from veadk.utils.patches import patch_adk_sync_tool_thread_pool


def _ctx(agent: LlmAgent, run_config: RunConfig) -> InvocationContext:
    return InvocationContext(
        session_service=InMemorySessionService(),
        invocation_id="inv-1",
        agent=agent,
        session=Session(
            id="session-1",
            appName="app",
            userId="user",
            state={},
            events=[],
        ),
        run_config=run_config,
    )


async def _run_two_sync_tool_calls(
    run_config: RunConfig,
    *,
    tool_name: str = "blocking_tool",
    agent_tool_thread_pool_config: ToolThreadPoolConfig | None = None,
) -> tuple[float, float, dict[str, int | None]]:
    starts: dict[str, float] = {}
    parallel_call_counts: dict[str, int | None] = {}

    def blocking_tool(label: str, delay: float, tool_context: ToolContext) -> dict:
        starts[label] = time.perf_counter()
        parallel_call_counts[label] = getattr(
            tool_context, "_veadk_parallel_tool_call_count", None
        )
        time.sleep(delay)
        return {"label": label}

    def run_code(label: str, delay: float, tool_context: ToolContext) -> dict:
        return blocking_tool(label, delay, tool_context)

    tool = FunctionTool(run_code if tool_name == "run_code" else blocking_tool)
    if agent_tool_thread_pool_config is None:
        agent = LlmAgent(
            name="agent",
            model="gemini-2.5-flash",
            tools=[tool],
        )
    else:
        agent = Agent(
            name="agent",
            model_name="test-model",
            model_provider="openai",
            model_api_key="test-key",
            model_api_base="http://example.com",
            tools=[tool],
            tool_thread_pool_config=agent_tool_thread_pool_config,
        )
    ctx = _ctx(agent, run_config)

    started_at = time.perf_counter()
    response_event = await functions.handle_function_call_list_async(
        ctx,
        [
            types.FunctionCall(
                id="call-a",
                name=tool_name,
                args={"label": "a", "delay": 0.2},
            ),
            types.FunctionCall(
                id="call-b",
                name=tool_name,
                args={"label": "b", "delay": 0.2},
            ),
        ],
        {tool_name: tool},
    )
    elapsed = time.perf_counter() - started_at

    assert response_event is not None
    assert len(response_event.get_function_responses()) == 2
    assert set(starts) == {"a", "b"}

    start_gap = abs(starts["b"] - starts["a"])
    return start_gap, elapsed, parallel_call_counts


@pytest.mark.asyncio
async def test_sync_tool_calls_stay_serial_without_thread_pool_config(
    monkeypatch,
) -> None:
    monkeypatch.setenv("VEADK_TOOL_THREAD_POOL_MAX_WORKERS", "2")
    patch_adk_sync_tool_thread_pool()

    start_gap, elapsed, _ = await _run_two_sync_tool_calls(RunConfig(max_llm_calls=5))

    assert start_gap >= 0.18
    assert elapsed >= 0.38


@pytest.mark.asyncio
async def test_sync_tool_calls_use_agent_thread_pool_when_configured() -> None:
    patch_adk_sync_tool_thread_pool()

    start_gap, elapsed, _ = await _run_two_sync_tool_calls(
        RunConfig(max_llm_calls=5),
        agent_tool_thread_pool_config=ToolThreadPoolConfig(max_workers=2),
    )

    assert start_gap < 0.1
    assert elapsed < 0.35


@pytest.mark.asyncio
async def test_sync_tool_calls_use_thread_pool_when_configured() -> None:
    patch_adk_sync_tool_thread_pool()

    start_gap, elapsed, _ = await _run_two_sync_tool_calls(
        RunConfig(
            max_llm_calls=5,
            tool_thread_pool_config=ToolThreadPoolConfig(max_workers=2),
        )
    )

    assert start_gap < 0.1
    assert elapsed < 0.35


@pytest.mark.asyncio
async def test_run_code_calls_stay_serial_without_thread_pool_config(
    monkeypatch,
) -> None:
    monkeypatch.setenv("VEADK_RUN_CODE_THREAD_POOL_MAX_WORKERS", "4")
    patch_adk_sync_tool_thread_pool()

    start_gap, elapsed, parallel_call_counts = await _run_two_sync_tool_calls(
        RunConfig(max_llm_calls=5),
        tool_name="run_code",
    )

    assert start_gap >= 0.18
    assert elapsed >= 0.38
    assert parallel_call_counts == {"a": None, "b": None}


@pytest.mark.asyncio
async def test_run_code_uses_agent_thread_pool_when_configured() -> None:
    patch_adk_sync_tool_thread_pool()

    start_gap, elapsed, parallel_call_counts = await _run_two_sync_tool_calls(
        RunConfig(max_llm_calls=5),
        tool_name="run_code",
        agent_tool_thread_pool_config=ToolThreadPoolConfig(max_workers=2),
    )

    assert start_gap < 0.1
    assert elapsed < 0.35
    assert parallel_call_counts == {"a": 2, "b": 2}
