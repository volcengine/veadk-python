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

"""Run independent specialists concurrently, then combine their findings.

The first stage uses `ParallelAgent` because the benefits and risks can be
analyzed independently. A `SequentialAgent` then runs the synthesizer after
both parallel branches have stored their results in shared session state.
"""

import asyncio

from veadk import Agent, Runner
from veadk.agents.parallel_agent import ParallelAgent
from veadk.agents.sequential_agent import SequentialAgent
from veadk.memory.short_term_memory import ShortTermMemory


def build_pipeline() -> SequentialAgent:
    benefits_analyst = Agent(
        name="benefits_analyst",
        instruction=(
            "Analyze the user's proposal. Return the three strongest benefits, "
            "including the likely impact of each one."
        ),
        output_key="benefits",
    )

    risks_analyst = Agent(
        name="risks_analyst",
        instruction=(
            "Analyze the user's proposal. Return the three most important risks "
            "and one practical mitigation for each risk."
        ),
        output_key="risks",
    )

    independent_analysis = ParallelAgent(
        name="independent_analysis",
        description="Analyzes benefits and risks concurrently.",
        sub_agents=[benefits_analyst, risks_analyst],
    )

    synthesizer = Agent(
        name="synthesizer",
        instruction=(
            "Turn the analyses below into a concise decision brief. Include a "
            "recommendation, the main trade-off, and one next step.\n\n"
            "Benefits:\n{benefits}\n\nRisks:\n{risks}"
        ),
        output_key="decision_brief",
    )

    return SequentialAgent(
        name="parallel_decision_pipeline",
        description="Runs independent analyses in parallel, then combines them.",
        sub_agents=[independent_analysis, synthesizer],
    )


async def main() -> None:
    pipeline = build_pipeline()
    runner = Runner(
        agent=pipeline,
        short_term_memory=ShortTermMemory(),
        app_name="parallel_multi_agent_demo",
    )

    result = await runner.run(
        messages="Should our engineering team adopt a four-day on-call rotation?",
        session_id="parallel-demo-session",
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
