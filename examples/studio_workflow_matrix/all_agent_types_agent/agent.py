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

"""Natural-output Studio fixture containing every supported agent type."""

from veadk import Agent
from veadk.agents.loop_agent import LoopAgent
from veadk.agents.parallel_agent import ParallelAgent
from veadk.agents.sequential_agent import SequentialAgent


def analysis_agent(name: str, role: str, output_key: str) -> Agent:
    """Build a tool-free specialist that emits natural user-facing prose."""
    return Agent(
        name=name,
        description=f"Handles the {role} stage of the combined workflow.",
        instruction=(
            f"Act as the {role} specialist. Answer in the user's language with "
            "concise, self-contained prose. Do not use bracketed stage labels, "
            "internal agent names, test markers, tools, or delegation."
        ),
        output_key=output_key,
    )


opening = analysis_agent(
    "all_types_opening",
    "problem framing",
    "all_types_opening",
)

sequential_stage = SequentialAgent(
    name="all_types_sequence",
    description="Builds the evaluation criteria in two ordered steps.",
    sub_agents=[
        analysis_agent(
            "all_types_context",
            "context and assumptions",
            "all_types_context",
        ),
        analysis_agent(
            "all_types_criteria",
            "decision criteria",
            "all_types_criteria",
        ),
    ],
)

parallel_stage = ParallelAgent(
    name="all_types_parallel",
    description="Analyzes evidence, risks, options, and rollout concurrently.",
    sub_agents=[
        analysis_agent(
            "all_types_evidence",
            "facts and evidence",
            "all_types_evidence",
        ),
        analysis_agent(
            "all_types_risks",
            "risks and mitigations",
            "all_types_risks",
        ),
        analysis_agent(
            "all_types_options",
            "alternative options",
            "all_types_options",
        ),
        analysis_agent(
            "all_types_rollout",
            "implementation planning",
            "all_types_rollout",
        ),
    ],
)

loop_stage = LoopAgent(
    name="all_types_review_loop",
    description="Reviews the draft twice before the final recommendation.",
    max_iterations=2,
    sub_agents=[
        analysis_agent(
            "all_types_reviewer",
            "quality review",
            "all_types_review",
        ),
    ],
)

final_response = Agent(
    name="all_types_final_response",
    description="Produces the final recommendation for the user.",
    instruction=(
        "Give the user one coherent final answer in their language. Synthesize the "
        "available facts, risks, decision criteria, and review feedback. Clearly "
        "separate facts, risks, and recommendations using natural headings. Do not "
        "print internal agent names, bracketed stage labels, or test markers."
    ),
    output_key="all_types_final",
)

root_agent = SequentialAgent(
    name="all_agent_types_agent",
    description=(
        "Combines LLM, sequential, parallel, and loop agents into one workflow."
    ),
    sub_agents=[
        opening,
        sequential_stage,
        parallel_stage,
        loop_stage,
        final_response,
    ],
)
