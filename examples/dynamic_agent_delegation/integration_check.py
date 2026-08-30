# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Credential-backed smoke checks for the dynamic delegation example."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from google.adk.runners import InMemoryRunner

from agent import root_agent


def _is_five(value: str) -> bool:
    try:
        return float(value.strip()) == 5
    except ValueError:
        return False


async def _run_case(
    runner: InMemoryRunner,
    *,
    session_id: str,
    prompt: str,
) -> dict[str, Any]:
    events = await runner.run_debug(
        prompt,
        user_id="integration-user",
        session_id=session_id,
        quiet=True,
    )
    calls = [
        call.name for event in events for call in (event.get_function_calls() or [])
    ]
    transfers = [
        event.actions.transfer_to_agent
        for event in events
        if event.actions.transfer_to_agent
    ]
    texts = [
        part.text
        for event in events
        if event.content
        for part in (event.content.parts or [])
        if part.text
    ]
    collected_refs = {
        resource["ref"]
        for event in events
        for response in (event.get_function_responses() or [])
        if response.name == "collect_resources"
        for resource in (response.response or {}).get("resources", [])
    }
    selected_refs = {
        ref
        for event in events
        for call in (event.get_function_calls() or [])
        if call.name == "create_agents"
        for agent in (call.args or {}).get("agents", [])
        for node in agent.get("nodes", [])
        for ref in node.get("resources", [])
    }
    return {
        "calls": calls,
        "transfers": transfers,
        "authors": [event.author for event in events],
        "final_text": texts[-1] if texts else "",
        "resource_refs_valid": selected_refs <= collected_refs,
        "has_error": any(event.error_message for event in events),
    }


async def main() -> None:
    runner = InMemoryRunner(
        agent=root_agent,
        app_name="dynamic_agent_delegation",
    )
    direct = await _run_case(
        runner,
        session_id="dynamic-agent-direct",
        prompt="你好，请用一句话介绍你自己。",
    )
    delegated = await _run_case(
        runner,
        session_id="dynamic-agent-delegated",
        prompt="请把任务移交给一个子智能体：计算 17 乘以 23，并只返回计算结果。",
    )
    custom_tool = await _run_case(
        runner,
        session_id="dynamic-agent-python-tool",
        prompt=(
            "请先收集资源，再创建一个子智能体。你必须在 python_tools 中编写并"
            "绑定一个计算中位数的完整 Python 工具，由子智能体调用它计算 "
            "[3, 9, 2, 7, 5]，最后只告诉我结果。"
        ),
    )
    missing_resource = await _run_case(
        runner,
        session_id="dynamic-agent-missing-resource",
        prompt=(
            "先收集资源，再尝试使用名为 definitely_missing_skill 的 Skill；如果"
            "资源列表中不存在，不要编造资源引用，直接说明无法绑定该 Skill。"
        ),
    )

    checks = {
        "direct-simple-response": not direct["calls"] and bool(direct["final_text"]),
        "discover-and-delegate": (
            delegated["calls"][:2] == ["collect_resources", "create_agents"]
            and bool(delegated["transfers"])
            and delegated["final_text"].strip() == "391"
        ),
        "delegated-custom-tool": (
            custom_tool["calls"][:2] == ["collect_resources", "create_agents"]
            and len(custom_tool["calls"]) >= 3
            and bool(custom_tool["transfers"])
            and _is_five(custom_tool["final_text"])
        ),
        "missing-resource-is-not-invented": (
            missing_resource["resource_refs_valid"]
            and not missing_resource["has_error"]
            and bool(missing_resource["final_text"])
        ),
    }
    report = {
        "total_cases": len(checks),
        "passed_cases": sum(checks.values()),
        "accuracy": sum(checks.values()) / len(checks),
        "exception_count": 0,
        "checks": checks,
    }
    print(json.dumps(report, ensure_ascii=False))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
