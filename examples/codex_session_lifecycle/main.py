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

"""A `runtime="codex"` session end to end: tools, sandbox, streaming, steering,
cancellation and resume.

One session, three invocations:

1. Plan a trip. Codex calls an MCP tool (weather) and a Python function tool
   (city research), follows a skill's reply style, and writes the plan to
   `plan.md` in its sandboxed workspace. The answer streams as it is written.
   While the research tool runs, `runner.steer()` adds an instruction to the
   turn in flight.
2. Start a second request and cancel it: the Codex turn is interrupted.
3. Ask about the earlier work: the session's Codex thread is resumed, so Codex
   answers from its own history and the files it wrote.

Sessions live in SQLite, so the Codex thread (saved with the session) also
survives a process restart: run the script twice to see turn 3 of the first
run's session resumed by the second.

Run:
    python examples/codex_session_lifecycle/main.py

Requires ``pip install "veadk-python[codex]"`` and a Responses-capable model
(Volcengine Ark or OpenAI) via ``MODEL_AGENT_API_KEY`` / ``MODEL_AGENT_API_BASE``
/ ``MODEL_AGENT_NAME``.
"""

import asyncio
import os
import sys
from pathlib import Path

from google.adk.skills import load_skill_from_dir
from google.adk.tools.mcp_tool.mcp_session_manager import StdioServerParameters
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.skill_toolset import SkillToolset
from google.genai import types

from veadk import Agent, Runner
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.runtime.codex import current_workspace

# Reuse the sibling example's skill and MCP server.
_SIBLING = Path(__file__).resolve().parent.parent / "codex_with_skill_and_mcp"
_SESSION_ID = "trip-planning"
_DATABASE = "/tmp/veadk_codex_session_lifecycle.db"

# Set while the research tool runs, so the demo can steer the turn right then.
_researching = asyncio.Event()


async def research_city(city: str) -> dict:
    """Look up the must-see places of a city.

    Args:
        city (str): The city to research.

    Returns:
        dict: Highlights of the city.
    """
    _researching.set()
    await asyncio.sleep(3)  # a slow lookup: the window in which we steer
    workspace = current_workspace()  # the turn's sandbox directory, if any
    return {
        "city": city,
        "highlights": ["Forbidden City", "Temple of Heaven", "Hutong walk"],
        "workspace": workspace,
    }


def build_agent() -> Agent:
    return Agent(
        name="trip_planner",
        description="Plans short city trips.",
        instruction=(
            "Plan trips. Use the weather tool and research_city, then save the "
            "plan as plan.md in the working directory with a shell command."
        ),
        runtime="codex",
        model_name=os.getenv("MODEL_AGENT_NAME", "deepseek-v4-pro-260425"),
        model_api_base=os.getenv(
            "MODEL_AGENT_API_BASE", "https://ark.cn-beijing.volces.com/api/v3"
        ),
        model_api_key=os.getenv("MODEL_AGENT_API_KEY"),
        tools=[
            SkillToolset(
                skills=[load_skill_from_dir(str(_SIBLING / "skills" / "weather-style"))]
            ),
            MCPToolset(
                connection_params=StdioServerParameters(
                    command=sys.executable, args=[str(_SIBLING / "mcp_server.py")]
                )
            ),
            research_city,
        ],
        codex_runtime_config={
            # Defaults, spelled out: Ark is called directly and the session's
            # Codex thread is resumed on every turn.
            "model_transport": "auto",
            "thread_mode": "resume",
            "sandbox": "workspace_write",
            "turn_timeout_seconds": 300,
        },
    )


async def ask(runner: Runner, text: str) -> None:
    print(f"\nUser: {text}\nAgent: ", end="", flush=True)
    async for event in runner.run_async(
        user_id=runner.user_id,
        session_id=_SESSION_ID,
        new_message=types.Content(role="user", parts=[types.Part(text=text)]),
    ):
        for call in event.get_function_calls() or []:
            print(f"\n  [tool] {call.name}", flush=True)
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
            if part.text and not part.thought and event.partial:
                print(part.text, end="", flush=True)  # stream the answer
    print()


async def main() -> None:
    runner = Runner(
        agent=build_agent(),
        short_term_memory=ShortTermMemory(
            backend="sqlite", local_database_path=_DATABASE
        ),
    )
    # Reuse the session across runs: its Codex thread is stored with it.
    session = await runner.session_service.get_session(
        app_name=runner.app_name, user_id=runner.user_id, session_id=_SESSION_ID
    )
    if session is None:
        await runner.short_term_memory.create_session(
            app_name=runner.app_name, user_id=runner.user_id, session_id=_SESSION_ID
        )

    # 1. Tools, skill, sandbox, streaming -- and a steer mid-turn.
    turn = asyncio.create_task(
        ask(runner, "Plan a 2-day Beijing trip and save it to plan.md.")
    )
    await _researching.wait()
    delivered = await runner.steer(_SESSION_ID, "Also add a short packing list.")
    print(f"\n  [steer] delivered to the running turn: {delivered}")
    await turn

    # 2. Cancel a request whose Codex turn is running (it is inside the research
    # tool): the turn is interrupted, and the next request still works.
    _researching.clear()
    turn = asyncio.create_task(ask(runner, "Now plan Shanghai the same way."))
    await _researching.wait()
    turn.cancel()
    try:
        await turn
    except asyncio.CancelledError:
        print("\n  [cancel] the Shanghai request was cancelled")

    # 3. Resume: Codex answers from its own thread and workspace.
    await ask(runner, "What did you save earlier, and what is in plan.md?")


if __name__ == "__main__":
    asyncio.run(main())
