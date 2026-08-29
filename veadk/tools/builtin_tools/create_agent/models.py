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
ResourceKind = Literal["skill", "knowledge_base"]
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
            "It runs in the host process without sandboxing."
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

    id: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    type: Literal["llm"]
    description: str = ""
    instruction: str
    model_name: str | list[str] | None = None
    model_provider: str | None = None
    model_api_base: str | None = None
    resources: list[str] = Field(
        default_factory=list,
        description="Resource refs returned by collect_resources.",
    )
    python_tools: list[PythonToolSpec] = Field(default_factory=list)


class SequentialAgentNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    type: Literal["sequential"]
    description: str = ""
    children: list[str] = Field(min_length=1)


class ParallelAgentNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    type: Literal["parallel"]
    description: str = ""
    children: list[str] = Field(min_length=1)


class LoopAgentNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    type: Literal["loop"]
    description: str = ""
    children: list[str] = Field(min_length=1)
    max_iterations: int = Field(default=3, ge=1)


class WorkflowEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    route: RouteValue | list[RouteValue] | None = None


class WorkflowAgentNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    type: Literal["workflow"]
    description: str = ""
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

    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    task: str
    root_node: str
    nodes: list[LegacyAgentNode] = Field(min_length=1)


class AgentBlueprint(BaseModel):
    """One independently constructed and executed root agent."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    task: str
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

    collection_id: str
    agents: list[AgentBlueprint] = Field(min_length=1)


class LegacyCreateAgentsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection_id: str
    agents: list[LegacyAgentBlueprint] = Field(min_length=1)


class CreatedAgentResult(BaseModel):
    name: str
    root_type: AgentType | None = None
    status: Literal["completed", "failed"]
    output: str | None = None
    error: str | None = None


class CreateAgentsResponse(BaseModel):
    collection_id: str
    results: list[CreatedAgentResult]
