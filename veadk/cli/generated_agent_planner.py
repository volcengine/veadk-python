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

"""Generate a validated recursive AgentDraft from a natural-language request."""

from __future__ import annotations

import asyncio
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from veadk import Agent, Runner
from veadk.cli.generated_agent_codegen import AgentDraft, CustomTool, MemoryConfig

PLANNER_MODEL_NAME = "doubao-seed-2-0-lite-260428"
DEFAULT_GENERATED_MODEL_NAME = "doubao-seed-2-1-pro-260628"


class GeneratedCustomToolPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Python function name in snake_case.")
    description: str = Field(description="What the generated tool stub should do.")


class GeneratedAgentPlan(BaseModel):
    """Strict recursive subset of the Studio AgentDraft contract."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Globally unique Python identifier in snake_case.")
    description: str = Field(description="Concise description of this Agent's role.")
    instruction: str = Field(
        description="Detailed system prompt for an llm Agent; empty for an orchestrator."
    )
    agentType: Literal["llm", "sequential", "parallel", "loop"]
    maxIterations: int = Field(
        description="Positive loop limit; use 3 for non-loop Agents."
    )
    modelName: Literal["", "doubao-seed-2-1-pro-260628"] = Field(
        description="Fixed model for an llm Agent; empty for an orchestrator."
    )
    builtinTools: list[
        Literal[
            "web_search",
            "parallel_web_search",
            "link_reader",
            "image_generate",
            "image_edit",
            "video_generate",
            "run_code",
        ]
    ]
    customTools: list[GeneratedCustomToolPlan]
    subAgents: list[GeneratedAgentPlan]

    @model_validator(mode="before")
    @classmethod
    def normalize_orchestrator_fields(cls, value: object) -> object:
        if not isinstance(value, dict) or value.get("agentType") == "llm":
            return value
        normalized = dict(value)
        normalized.update(
            instruction="",
            modelName="",
            builtinTools=[],
            customTools=[],
        )
        return normalized

    @model_validator(mode="after")
    def validate_agent_shape(self) -> GeneratedAgentPlan:
        if self.maxIterations < 1:
            raise ValueError(f"{self.name} has an invalid maxIterations")
        if self.agentType == "llm":
            if not self.instruction.strip() or not self.modelName:
                raise ValueError(f"{self.name} is missing llm configuration")
            if self.subAgents:
                raise ValueError(f"llm Agent {self.name} must be a leaf")
        else:
            if not self.subAgents:
                raise ValueError(f"orchestrator {self.name} has no sub-Agents")
            if self.instruction or self.modelName or self.builtinTools:
                raise ValueError(
                    f"orchestrator {self.name} contains llm-only configuration"
                )
            if self.customTools:
                raise ValueError(
                    f"orchestrator {self.name} contains leaf-only capabilities"
                )
        return self


class GeneratedAgentDraftPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(description="One-sentence summary of the generated design.")
    rootAgent: GeneratedAgentPlan
    unresolvedItems: list[str] = Field(
        description="Real resource choices or identifiers the user must still provide."
    )


class GeneratedAgentDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement: str = Field(min_length=4, max_length=8000)


PLANNER_INSTRUCTION = f"""
You convert a user's requirement into a complete recursive VeADK Agent plan.

Rules:
- Use only llm, sequential, parallel, and loop Agent types.
- Preserve the user's execution order. Use parallel only for work that can run
  concurrently, sequential for ordered stages, and loop for bounded iteration.
- An llm Agent is always a leaf. Fill its name, description, detailed
  instruction, model, and tools.
- Every llm Agent uses modelName {DEFAULT_GENERATED_MODEL_NAME}.
- An orchestrator only schedules subAgents. Its instruction and modelName are
  empty and its tools are empty.
- Use maxIterations=3 except when the user requests a loop limit.
- Use globally unique Python snake_case Agent and custom-tool names.
- web_search and parallel_web_search find public Internet results. link_reader
  reads the original page.
- image_generate creates images from text prompts. image_edit modifies an
  existing image. video_generate creates video from text or image inputs.
  run_code executes code in a sandbox.
- Select only tools the Agent will actually invoke. Media planning or review
  Agents do not need generation tools unless they generate or edit that media.
- Enable tools only where the requirement needs them.
- Do not invent instance IDs, URLs, credentials, MCP servers, or skill IDs.
  Put real resources that still need user input in unresolvedItems.
""".strip()


def _to_agent_draft(plan: GeneratedAgentPlan) -> AgentDraft:
    return AgentDraft(
        name=plan.name,
        description=plan.description,
        instruction=plan.instruction,
        agentType=plan.agentType,
        maxIterations=plan.maxIterations,
        modelName=plan.modelName,
        builtinTools=list(plan.builtinTools),
        customTools=[CustomTool(**tool.model_dump()) for tool in plan.customTools],
        memory=MemoryConfig(shortTerm=False, longTerm=False),
        shortTermBackend="local",
        longTermBackend="local",
        autoSaveSession=False,
        knowledgebase=False,
        knowledgebaseBackend="viking",
        tracing=False,
        tracingExporters=[],
        subAgents=[_to_agent_draft(child) for child in plan.subAgents],
    )


async def generate_agent_draft(requirement: str) -> dict:
    """Call Ark with a strict output schema and return a Studio AgentDraft."""

    planner = Agent(
        name="studio_agent_draft_planner",
        description="Builds a validated recursive Studio Agent configuration.",
        instruction=PLANNER_INSTRUCTION,
        model_name=PLANNER_MODEL_NAME,
        output_schema=GeneratedAgentDraftPlan,
        enable_responses=True,
        enable_responses_cache=False,
        model_extra_config={"extra_body": {"thinking": {"type": "disabled"}}},
    )
    runner = Runner(agent=planner, app_name="studio_agent_draft_planner")
    raw = await asyncio.wait_for(
        runner.run(
            requirement,
            session_id=f"studio-agent-draft-{uuid4().hex}",
        ),
        timeout=180,
    )
    plan = GeneratedAgentDraftPlan.model_validate_json(raw)
    return {
        "draft": _to_agent_draft(plan.rootAgent).model_dump(),
        "summary": plan.summary,
        "unresolvedItems": plan.unresolvedItems,
    }
