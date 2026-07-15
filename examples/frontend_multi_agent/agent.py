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

"""A multi-agent app for trying the web UI's live topology panel.

Structure:

    coordinator (LLM)                 ← routes by delegating (transfer_to_agent)
    ├─ math_tutor      (LLM)
    ├─ poet            (LLM)
    └─ research_team   (Sequential)   ← runs its steps in order
       ├─ planner      (LLM)
       └─ writer       (LLM)

Ask a math question / for a poem / to research something, and watch the
conversation-side topology panel: it highlights whichever agent is executing
(from the stream's `author`) and shows the delegation path as the coordinator
hands off (`transfer_to_agent`). The research request additionally shows a
Sequential sub-team running planner → writer.

Run it:

    export MODEL_AGENT_API_KEY=...
    export MODEL_AGENT_API_BASE=https://ark.cn-beijing.volces.com/api/v3
    export MODEL_AGENT_NAME=deepseek-v4-flash-260425
    veadk frontend --open        # from the parent folder (examples/)
    # then pick the "frontend_multi_agent" app in the picker
"""

from veadk import Agent
from veadk.agents.sequential_agent import SequentialAgent

# --- leaf specialists ------------------------------------------------------
math_tutor = Agent(
    name="math_tutor",
    description="Solves math problems and explains the steps.",
    instruction=(
        "You are a patient math tutor. Solve the user's math problem and show "
        "the key steps briefly. Answer in the user's language."
    ),
)

poet = Agent(
    name="poet",
    description="Writes short poems on a given theme.",
    instruction=(
        "You are a poet. Write a short (4-8 line) poem on the user's theme. "
        "Answer in the user's language."
    ),
)

# --- a nested Sequential team: plan, then write ----------------------------
planner = Agent(
    name="planner",
    description="Breaks a research question into a short plan.",
    instruction=(
        "You plan research. Given the user's question, output a tight 3-point "
        "plan of what to cover (bullets only)."
    ),
    output_key="research_plan",
)

writer = Agent(
    name="writer",
    description="Writes the answer from the research plan.",
    instruction=(
        "You are a writer. Using this plan, write a concise, well-structured "
        "answer to the user's question:\n\n{research_plan}"
    ),
)

research_team = SequentialAgent(
    name="research_team",
    description=(
        "Handles research / explanation requests by planning first, then "
        "writing the answer."
    ),
    sub_agents=[planner, writer],
)

# --- root coordinator: delegates to the right specialist -------------------
coordinator = Agent(
    name="coordinator",
    description="Routes the user's request to the right specialist agent.",
    instruction=(
        "You are a coordinator that routes work to sub-agents. Do NOT answer "
        "directly. Based on the user's request, transfer to the best agent:\n"
        "- math / calculations  -> math_tutor\n"
        "- a poem / creative writing  -> poet\n"
        "- research, explanations, 'tell me about ...'  -> research_team\n"
        "If nothing fits, pick the closest one."
    ),
    sub_agents=[math_tutor, poet, research_team],
)

# Required by the Google ADK agent loader.
root_agent = coordinator
