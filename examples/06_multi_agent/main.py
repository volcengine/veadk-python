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

"""Compose several agents into a workflow with `SequentialAgent`.

Instead of one agent doing everything, we split the job into specialists that
run in a fixed order:

    outliner  ->  writer  ->  editor

State is shared between them. Each sub-agent writes its result to the session
state via `output_key`, and the next agent reads it by referencing `{that_key}`
in its instruction. The `SequentialAgent` just runs them top to bottom.
"""

import asyncio

from veadk import Agent, Runner
from veadk.agents.sequential_agent import SequentialAgent
from veadk.memory.short_term_memory import ShortTermMemory


def build_pipeline() -> SequentialAgent:
    outliner = Agent(
        name="outliner",
        instruction=(
            "You are an outliner. Given the user's topic, produce a tight "
            "3-point outline (just the bullet points, no prose)."
        ),
        output_key="outline",
    )

    writer = Agent(
        name="writer",
        instruction=(
            "You are a writer. Expand the following outline into a short, "
            "engaging paragraph (~120 words):\n\n{outline}"
        ),
        output_key="draft",
    )

    editor = Agent(
        name="editor",
        instruction=(
            "You are an editor. Polish the draft below for clarity and flow, "
            "then return ONLY the final text:\n\n{draft}"
        ),
        output_key="final",
    )

    return SequentialAgent(
        name="content_pipeline",
        description="Turns a topic into a polished short paragraph.",
        sub_agents=[outliner, writer, editor],
    )


async def main() -> None:
    pipeline = build_pipeline()
    # Workflow agents (Sequential/Parallel/Loop) don't carry their own memory, so
    # give the Runner a session store explicitly.
    runner = Runner(
        agent=pipeline,
        short_term_memory=ShortTermMemory(),
        app_name="multi_agent_demo",
    )

    final_text = await runner.run(
        messages="主题：为什么团队应该写好的提交信息（commit message）。",
        session_id="demo-session",
    )
    print(final_text)


if __name__ == "__main__":
    asyncio.run(main())
