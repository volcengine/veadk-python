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
from typing import Any, Literal
from uuid import uuid4

from google.adk.tools import ToolContext
from pydantic import BaseModel, ConfigDict, Field, model_validator

from veadk import Agent, Runner
from veadk.cli.generated_agent_codegen import AgentDraft, CustomTool, MemoryConfig
from veadk.consts import DEFAULT_MODEL_AGENT_NAME
from veadk.utils.cloud_provider import cloud_provider_from_env

PLANNER_MODEL_NAME = (
    "seed-2-0-lite-260228"
    if cloud_provider_from_env() == "byteplus"
    else "doubao-seed-2-0-lite-260428"
)
DEFAULT_GENERATED_MODEL_NAME = DEFAULT_MODEL_AGENT_NAME
GENERATED_AGENT_CONVERSATION_APP_NAME = "studio_agent_creation_assistant"
GENERATED_AGENT_RESULT_STATE_KEY = "studio_generated_agent_result"
GENERATED_AGENT_CONVERSATION_TIMEOUT_SECONDS = 240


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
    modelName: Literal[
        "",
        "doubao-seed-2-1-pro-260628",
        "seed-2-0-lite-260228",
    ] = Field(description="Fixed model for an llm Agent; empty for an orchestrator.")
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
            if self.modelName != DEFAULT_GENERATED_MODEL_NAME:
                raise ValueError(f"{self.name} must use {DEFAULT_GENERATED_MODEL_NAME}")
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


class GeneratedAgentConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    session_id: str = Field(
        alias="sessionId",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    message: str = Field(min_length=1, max_length=8000)


PLANNER_INSTRUCTION = f"""
You convert a user's requirement into a complete recursive VeADK Agent plan.

Rules:
- Use only llm, sequential, parallel, and loop Agent types.
- Prefer an llm Agent as rootAgent so it can reason and respond directly and
  flexibly to the user. Do not choose an orchestrator merely because the
  requirement mentions multiple tasks or steps. Use an orchestrator as the
  root only when strict workflow control is essential to the requested result.
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


CONVERSATION_INSTRUCTION = """
你是 AgentKit Studio 的智能体创建助手。你的首要职责是与用户自然对话，逐步理解他们
希望创建或修改的 Agent，而不是把每句话都当成最终配置指令。

规则：
- 正常回答问候、解释、讨论和澄清问题，不要调用工具。
- 当用户明确要求创建、生成或更新 Agent，并且需求已经足够具体时，调用
  `generate_agent`。不要要求用户提供实现中可以合理推断的细枝末节。
- 调用工具时，把本轮对话中已经确认的完整需求整理成一段自包含的 requirement，
  不要只传用户最后一句话。
- 工具返回后，用简短自然语言说明已经生成或更新了什么；不要向用户展示原始 JSON。
- 如果工具返回 unresolvedItems，明确告诉用户还需要补充哪些真实资源或标识。
- 所有回复都使用适合当前聊天面板直接展示的纯文本，不要输出 Markdown 标记。
- 不要声称配置已经生成，除非本轮确实成功调用了 `generate_agent`。
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


async def generate_agent(requirement: str, tool_context: ToolContext) -> dict:
    """Generate a validated Agent configuration from the consolidated requirement.

    Call this tool only after the user's Agent requirements are sufficiently clear.
    The requirement must include all relevant constraints learned in the conversation.
    """

    result = await generate_agent_draft(requirement)
    stored_result = {
        "generationId": uuid4().hex,
        **result,
    }
    tool_context.state[GENERATED_AGENT_RESULT_STATE_KEY] = stored_result
    return result


def create_generated_agent_conversation_runner() -> Runner:
    """Create the stateful main chat Agent used by Studio's creation workspace."""

    assistant = Agent(
        name=GENERATED_AGENT_CONVERSATION_APP_NAME,
        description="Understands user needs and creates Agent configurations when ready.",
        instruction=CONVERSATION_INSTRUCTION,
        model_name=PLANNER_MODEL_NAME,
        tools=[generate_agent],
        enable_responses=True,
        enable_responses_cache=False,
    )
    return Runner(
        agent=assistant,
        app_name=GENERATED_AGENT_CONVERSATION_APP_NAME,
    )


async def run_generated_agent_conversation(
    runner: Runner,
    *,
    message: str,
    user_id: str,
    session_id: str,
) -> dict[str, Any]:
    """Run one conversational turn and return a newly generated draft, if any."""

    previous_session = await runner.session_service.get_session(
        app_name=GENERATED_AGENT_CONVERSATION_APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )
    previous_generation_id = (
        str(
            previous_session.state.get(GENERATED_AGENT_RESULT_STATE_KEY, {}).get(
                "generationId", ""
            )
        )
        if previous_session
        else ""
    )

    reply = await asyncio.wait_for(
        runner.run(message, user_id=user_id, session_id=session_id),
        timeout=GENERATED_AGENT_CONVERSATION_TIMEOUT_SECONDS,
    )

    current_session = await runner.session_service.get_session(
        app_name=GENERATED_AGENT_CONVERSATION_APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )
    stored_result = (
        current_session.state.get(GENERATED_AGENT_RESULT_STATE_KEY)
        if current_session
        else None
    )
    generated_result = (
        stored_result
        if isinstance(stored_result, dict)
        and stored_result.get("generationId") != previous_generation_id
        else None
    )

    response: dict[str, Any] = {"reply": reply.strip()}
    if generated_result:
        response.update(
            draft=generated_result.get("draft"),
            summary=generated_result.get("summary", ""),
            unresolvedItems=generated_result.get("unresolvedItems", []),
        )
        if not response["reply"]:
            response["reply"] = str(response["summary"] or "Agent 配置已生成。")
    elif not response["reply"]:
        response["reply"] = "我还需要了解更多需求，请继续说明。"
    return response
