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

"""A `runtime="codex"` agent that uses both a local skill and an MCP tool.

On a Codex runtime backed by a chat model (e.g. Volcengine Ark):

- **Skills** are materialized into Codex's on-disk skill directory and driven by
  Codex's native skill system.
- **MCP / function tools** can't be handed to Codex directly (Codex presents
  them to the model as a `namespace` tool the chat backend rejects), so the
  runtime's shim advertises them to the backend as plain functions and executes
  them itself.

Both are just normal VeADK/ADK wiring — the runtime handles the rest.

Run:
    python examples/codex_with_skill_and_mcp/main.py

Requires:
- ``pip install openai-codex`` (bundles the Codex CLI binary).
- Ark (or another OpenAI-compatible chat) credentials via ``MODEL_AGENT_API_KEY``
  / ``MODEL_AGENT_API_BASE`` / ``MODEL_AGENT_NAME`` (see the repo .env.example).
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

_HERE = Path(__file__).resolve().parent
_SKILL_DIR = _HERE / "skills" / "weather-style"
_MCP_SERVER = _HERE / "mcp_server.py"


def build_agent() -> Agent:
    # Skill: a local SKILL.md directory, loaded the ADK-native way. The codex
    # runtime materializes it into Codex's skill directory.
    skill_toolset = SkillToolset(skills=[load_skill_from_dir(str(_SKILL_DIR))])

    # MCP: a stdio MCP server launched as a subprocess. The codex runtime lists
    # its tools and executes them via the shim. Swap StdioServerParameters for
    # StreamableHTTPConnectionParams(url=...) to point at a remote MCP server.
    weather_mcp = MCPToolset(
        connection_params=StdioServerParameters(
            command=sys.executable, args=[str(_MCP_SERVER)]
        )
    )

    return Agent(
        name="codex_skill_mcp_agent",
        description="A codex-runtime agent with a skill and an MCP tool.",
        instruction="Help the user. Use your skills and tools when relevant.",
        runtime="codex",
        model_name=os.getenv("MODEL_AGENT_NAME", "deepseek-v4-flash-260425"),
        model_api_base=os.getenv(
            "MODEL_AGENT_API_BASE", "https://ark.cn-beijing.volces.com/api/v3"
        ),
        model_api_key=os.getenv("MODEL_AGENT_API_KEY"),
        tools=[skill_toolset, weather_mcp],
    )


async def main() -> None:
    agent = build_agent()
    runner = Runner(agent=agent, short_term_memory=ShortTermMemory())
    await runner.short_term_memory.create_session(
        app_name=runner.app_name, user_id=runner.user_id, session_id="s1"
    )

    question = "What's the weather in Beijing?"
    print(f"User: {question}\n")
    async for event in runner.run_async(
        user_id=runner.user_id,
        session_id="s1",
        new_message=types.Content(role="user", parts=[types.Part(text=question)]),
    ):
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
            if part.text and not part.thought:
                print(f"Agent: {part.text}")


if __name__ == "__main__":
    asyncio.run(main())
