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

"""Run the ClickZetta data agent examples through VeADK Runner."""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from veadk import Runner

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clickzetta_data_agent.agent import root_agent  # noqa: E402


DEFAULT_QUESTION = "北京二手房交易数据中，总交易量是多少？请给出简短结论。"

SCENARIOS = {
    "preflight": """
执行会前预检。必须严格串行调用：
1. get_clickzetta_status；
2. get_clickzetta_runtime_overview(limit=5)；
3. list_clickzetta_assets；
4. get_semantic_catalog。
不要调用业务问数或 SQL。最后给出 PASS/FAIL，并逐项说明依据。
""".strip(),
    "demo": f"""
执行标准 Agent + Data 演示。必须严格串行调用：
1. get_clickzetta_status；
2. get_clickzetta_runtime_overview(limit=5)；
3. get_semantic_catalog；
4. ask_clickzetta_analytics，问题是“{DEFAULT_QUESTION}”
最后只总结连接、运行概况、语义口径、答案和数据来源，不增加政策或因果推断。
""".strip(),
    "guardrail": """
执行只读 SQL 护栏演示。必须严格串行调用 run_readonly_sql 三次：
1. sql="SELECT 1"；
2. sql="DROP TABLE demo_customer_data"；
3. sql="SELECT 1; SELECT 2"。
最后说明哪些请求被允许、哪些被拦截，以及被拦截请求是否发往云器。
""".strip(),
}


def scenario_prompt(name: str) -> str:
    """Return the exact VeADK Agent prompt for a named demo scenario."""
    try:
        return SCENARIOS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown scenario: {name}") from exc


async def run_agent_prompt(
    prompt: str,
    *,
    runner_factory: Callable[..., Any] = Runner,
    session_id: str | None = None,
) -> Any:
    """Execute one prompt through the exported VeADK root Agent."""
    runner = runner_factory(agent=root_agent, app_name="clickzetta_data_agent")
    return await runner.run(
        messages=prompt,
        session_id=session_id or f"clickzetta-demo-{uuid.uuid4().hex[:8]}",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the VeADK ClickZetta read-only data agent demo."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true", help="Run preflight checks.")
    mode.add_argument("--demo", action="store_true", help="Run the standard demo.")
    mode.add_argument(
        "--guardrail-test",
        action="store_true",
        help="Verify the read-only SQL guardrail.",
    )
    mode.add_argument("--ask", metavar="QUESTION", help="Ask a custom question.")
    return parser.parse_args()


async def async_main() -> int:
    args = parse_args()
    if args.preflight:
        prompt = scenario_prompt("preflight")
    elif args.demo:
        prompt = scenario_prompt("demo")
    elif args.guardrail_test:
        prompt = scenario_prompt("guardrail")
    else:
        prompt = args.ask

    try:
        answer = await run_agent_prompt(prompt)
    except Exception as exc:
        print(f"VeADK Agent failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print("\n=== VeADK Agent final answer ===")
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main()))
