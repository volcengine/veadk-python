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

"""Public request and response models for the create-agent toolset."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


AgentType = Literal["llm", "sequential", "parallel", "loop", "workflow"]
ResourceKind = Literal["skill", "knowledge_base", "tool"]
RouteValue = str | int | bool


class AgentCapabilities(BaseModel):
    """Agent types supported by the installed Google ADK runtime."""

    google_adk_version: str
    agent_types: list[AgentType]
    max_orchestration_depth: int = 2


class ResourceDescriptor(BaseModel):
    """Serializable metadata for one discoverable resource."""

    ref: str
    kind: ResourceKind
    name: str
    description: str = ""
    source: str
    version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResourceSourceStatus(BaseModel):
    """Collection status for one independently queried source."""

    source: str
    status: Literal["ok", "skipped", "error"]
    count: int = 0
    message: str | None = None
    search_keywords: list[str] = Field(default_factory=list)


class CollectResourcesResponse(BaseModel):
    collection_id: str
    capabilities: AgentCapabilities
    resources: list[ResourceDescriptor] = Field(default_factory=list)
    sources: list[ResourceSourceStatus] = Field(default_factory=list)


class PythonToolSpec(BaseModel):
    """Trusted Python source executed without isolation in the current process."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    description: str
    code: str = Field(
        description=(
            "Trusted Python source defining the callable named by entrypoint. "
            "It runs in the host process without sandboxing. Every parameter, "
            "return value, and value crossing the tool boundary must survive a "
            "standard JSON round trip: object keys must be strings, tuple or "
            "object dictionary keys are forbidden, and composite keys such as "
            "item combinations must be represented as lists of records. Prefer "
            "direct reasoning instead of a temporary tool for small enumerable "
            "problems."
        )
    )
    entrypoint: str | None = Field(
        default=None,
        description="Callable to expose; defaults to name.",
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description=(
            "Installed Python distribution requirements to verify, for example "
            "['pandas>=2']. Missing packages are reported and never installed."
        ),
    )


class LlmAgentNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
        description=(
            "Stable, reusable snake_case capability identifier without "
            "request-specific entities, industries, sectors, verticals, or "
            "their acronyms. Keep only the operation or deliverable; exclude the "
            "target business domain, subject matter, content category, product "
            "type, technology category, protocol, or runtime environment. For "
            "example, use content_researcher instead of album_researcher and "
            "technology_researcher instead of database_researcher."
        ),
    )
    type: Literal["llm"]
    description: str = Field(
        default="",
        description=(
            "Reusable capability description without request-specific people, "
            "brands, products, platforms, industries, sectors, verticals, "
            "business domains, subject matters, content categories, languages, "
            "locales, topics, incidents, product or technology types, protocols, "
            "runtime environments, or filenames. Describe the operation against "
            "user-specified inputs instead: say 'researches the user-specified "
            "subject' rather than mentioning music or albums, and 'compares the "
            "user-specified technologies' rather than mentioning cloud databases."
        ),
    )
    instruction: str = Field(
        description=(
            "Durable role instructions that read the current user request and "
            "complete it, while parameterizing rather than hard-coding its "
            "specific entities, topic, issue, platform, product, industry, "
            "sector, vertical, business domain, subject matter, content category, "
            "product or technology type, protocol, runtime environment, acronym, "
            "source or target language, locale, or filename. Refer to them as "
            "user-specified inputs instead. Any concrete output-language requirement "
            "belongs only in AgentBlueprint.task, even when it matches the language "
            "used in the current request. Express it solely as 'respond in the "
            "user-specified language'; never name or infer the concrete language in "
            "reusable instructions. Never mention music, album, cloud, "
            "database, or another current subject merely to explain the role. "
            "For comparison roles, use the domain-neutral pattern: read the current "
            "request, research and compare the user-specified candidates against "
            "the requested criteria, and return a structured decision report. The "
            "blueprint task is the only carrier of concrete candidate details. A "
            "technology-comparison workflow uses evidence_researcher, "
            "criteria_evaluator, and decision_report_writer; its instructions refer "
            "only to user-specified candidates and requested evaluation criteria."
        )
    )
    model_name: str | list[str] | None = None
    model_provider: str | None = None
    model_api_base: str | None = None
    resources: list[str] = Field(
        default_factory=list,
        description=(
            "Every Skill, knowledge base, or VeADK built-in tool that this LLM "
            "node should use, expressed as an exact ref returned by "
            "collect_resources. Resources are not mounted automatically: include "
            "each relevant Skill ref explicitly, and leave Skills empty only when "
            "the collected results contain no Skill relevant to the node's task."
        ),
    )
    python_tools: list[PythonToolSpec] = Field(
        default_factory=list,
        description=(
            "Tools authored by the main agent as complete trusted Python source. "
            "These are separate from built-in tool refs in resources. Use only "
            "JSON-safe parameter and result schemas; never use tuple or other "
            "non-string dictionary keys across the tool boundary."
        ),
    )


class SequentialAgentNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
        description=(
            "Stable reusable operation identifier without the current subject "
            "matter, content category, product or technology type, protocol, or "
            "runtime environment."
        ),
    )
    type: Literal["sequential"]
    description: str = Field(
        default="",
        description=(
            "Reusable workflow role without the current subject matter, content "
            "category, product or technology type, protocol, or runtime environment."
        ),
    )
    children: list[str] = Field(min_length=1)


class ParallelAgentNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
        description=(
            "Stable reusable operation identifier without the current subject "
            "matter, content category, product or technology type, protocol, or "
            "runtime environment."
        ),
    )
    type: Literal["parallel"]
    description: str = Field(
        default="",
        description=(
            "Reusable workflow role without the current subject matter, content "
            "category, product or technology type, protocol, or runtime environment."
        ),
    )
    children: list[str] = Field(min_length=1)


class LoopAgentNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
        description=(
            "Stable reusable operation identifier without the current subject "
            "matter, content category, product or technology type, protocol, or "
            "runtime environment."
        ),
    )
    type: Literal["loop"]
    description: str = Field(
        default="",
        description=(
            "Reusable workflow role without the current subject matter, content "
            "category, product or technology type, protocol, or runtime environment."
        ),
    )
    children: list[str] = Field(min_length=1)
    max_iterations: int = Field(default=3, ge=1)


class WorkflowEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    route: RouteValue | list[RouteValue] | None = None


class WorkflowAgentNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
        description=(
            "Stable reusable operation identifier without the current subject "
            "matter, content category, product or technology type, protocol, or "
            "runtime environment."
        ),
    )
    type: Literal["workflow"]
    description: str = Field(
        default="",
        description=(
            "Reusable workflow role without the current subject matter, content "
            "category, product or technology type, protocol, or runtime environment."
        ),
    )
    edges: list[WorkflowEdge] = Field(min_length=1)
    max_concurrency: int | None = Field(default=None, ge=1)


LegacyAgentNode = Annotated[
    LlmAgentNode | SequentialAgentNode | ParallelAgentNode | LoopAgentNode,
    Field(discriminator="type"),
]

AgentNode = Annotated[
    LlmAgentNode
    | SequentialAgentNode
    | ParallelAgentNode
    | LoopAgentNode
    | WorkflowAgentNode,
    Field(discriminator="type"),
]


class LegacyAgentBlueprint(BaseModel):
    """One root agent definition for ADK versions without graph workflows."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
        description=(
            "Stable, reusable snake_case capability name. Do not include people, "
            "characters, brands, products, product categories, platforms, channels, "
            "industries, sectors, verticals, their acronyms, business domains, "
            "subject matters, content categories, languages, locales, organizations, "
            "places, dates, topics, one-off issues or incidents, document titles, "
            "filenames, URLs, or other request-specific entities."
        ),
    )
    task: str = Field(
        description=(
            "Complete one-off user objective, including its specific subjects, "
            "inputs, constraints, and required deliverable."
        )
    )
    root_node: str
    nodes: list[LegacyAgentNode] = Field(min_length=1)


class AgentBlueprint(BaseModel):
    """One independently constructed root agent."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
        description=(
            "Stable, reusable snake_case capability name. Do not include people, "
            "characters, brands, products, product categories, platforms, channels, "
            "industries, sectors, verticals, their acronyms, business domains, "
            "subject matters, content categories, languages, locales, organizations, "
            "places, dates, topics, one-off issues or incidents, document titles, "
            "filenames, URLs, or other request-specific entities."
        ),
    )
    task: str = Field(
        description=(
            "Complete one-off user objective, including its specific subjects, "
            "inputs, constraints, and required deliverable."
        )
    )
    root_node: str
    nodes: list[AgentNode] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_node_ids(self) -> "AgentBlueprint":
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("Node ids must be unique within one agent blueprint.")
        if self.root_node not in ids:
            raise ValueError(f"Root node '{self.root_node}' is not defined.")
        return self


class CreateAgentsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection_id: str = Field(
        description=(
            "ID returned by collect_resources. Use an empty string only when the "
            "user explicitly prohibits network, knowledge-base, and external-resource "
            "access; every LLM node must then have empty resources."
        )
    )
    agents: list[AgentBlueprint] = Field(min_length=1)
    handoff_to: str = Field(
        description=(
            "Name of the agent blueprint that should receive control after all "
            "agents have been created."
        )
    )

    @model_validator(mode="after")
    def validate_handoff_target(self) -> "CreateAgentsInput":
        _validate_agent_names_and_handoff(self.agents, self.handoff_to)
        return self


class LegacyCreateAgentsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection_id: str = Field(
        description=(
            "ID returned by collect_resources. Use an empty string only when the "
            "user explicitly prohibits network, knowledge-base, and external-resource "
            "access; every LLM node must then have empty resources."
        )
    )
    agents: list[LegacyAgentBlueprint] = Field(min_length=1)
    handoff_to: str = Field(
        description=(
            "Name of the agent blueprint that should receive control after all "
            "agents have been created."
        )
    )

    @model_validator(mode="after")
    def validate_handoff_target(self) -> "LegacyCreateAgentsInput":
        _validate_agent_names_and_handoff(self.agents, self.handoff_to)
        return self


class CreatedAgentResult(BaseModel):
    name: str
    runtime_name: str | None = None
    description: str = ""
    root_type: AgentType | None = None
    status: Literal["completed", "failed"]
    resources: list[ResourceDescriptor] = Field(default_factory=list)
    python_tools: list[PythonToolSpec] = Field(default_factory=list)
    output: str | None = None
    error: str | None = None


class CreateAgentsResponse(BaseModel):
    collection_id: str
    handoff_to: str | None = None
    results: list[CreatedAgentResult]


def _validate_agent_names_and_handoff(
    agents: list[AgentBlueprint] | list[LegacyAgentBlueprint],
    handoff_to: str,
) -> None:
    names = [agent.name for agent in agents]
    if len(names) != len(set(names)):
        raise ValueError("Agent blueprint names must be unique.")
    if handoff_to not in names:
        raise ValueError(f"handoff_to '{handoff_to}' must match one of agents[*].name.")
