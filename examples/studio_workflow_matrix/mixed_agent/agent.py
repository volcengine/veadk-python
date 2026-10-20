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

"""Combined LLM, Sequential, Parallel, and Loop Agent Studio fixture."""

from common import labelled_agent

from veadk import Agent
from veadk.agents.loop_agent import LoopAgent
from veadk.agents.parallel_agent import ParallelAgent
from veadk.agents.sequential_agent import SequentialAgent

opening = labelled_agent("mixed_opening", "opening", output_key="mixed_opening")

parallel_stage = ParallelAgent(
    name="mixed_parallel",
    description="Runs two middle-stage specialists concurrently.",
    sub_agents=[
        labelled_agent("mixed_facts", "facts", output_key="mixed_facts"),
        labelled_agent("mixed_risks", "risks", output_key="mixed_risks"),
    ],
)

loop_stage = LoopAgent(
    name="mixed_loop",
    description="Runs two bounded review iterations.",
    max_iterations=2,
    sub_agents=[
        labelled_agent("mixed_reviewer", "review", output_key="mixed_review"),
    ],
)

closing = Agent(
    name="mixed_closing",
    description="Produces the final combined workflow summary.",
    instruction=(
        "Summarize the completed opening, parallel, and review stages in concise, "
        "natural prose. Do not print internal agent names, bracketed stage labels, "
        "or test markers. Never call tools or delegate work."
    ),
    output_key="mixed_final",
)

root_agent = SequentialAgent(
    name="mixed_agent",
    description="Exercises LLM, Sequential, Parallel, and Loop agents together.",
    sub_agents=[opening, parallel_stage, loop_stage, closing],
)
