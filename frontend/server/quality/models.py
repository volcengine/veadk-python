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

"""Bounded request and structured output contracts for quality management."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Preference = Literal["trajectory", "outcome", "balanced"]
Text = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=6000)
]
ShortText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
]


class CapabilityContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ShortText
    description: str = Field(default="", max_length=3000)


class SkillContext(CapabilityContext):
    instructions: str = Field(default="", max_length=30000)
    source: str = Field(default="", max_length=100)
    version: str = Field(default="", max_length=300)


class ComponentContext(CapabilityContext):
    kind: str = Field(max_length=100)
    backend: str = Field(default="", max_length=300)
    source: str = Field(default="", max_length=300)
    provenance: Literal["runtime", "draft"]


class ConfigurationEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: ShortText
    value: str = Field(max_length=6000)


class McpServerContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: ShortText
    transport: str = Field(max_length=100)


class WorkflowEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_: ShortText = Field(alias="from")
    to: ShortText


class WorkflowContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: ShortText
    edges: list[WorkflowEdge] = Field(max_length=100)


class EnvironmentReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: ShortText
    version: ShortText


class EnvironmentSkill(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: ShortText
    version: str = Field(default="", max_length=300)


class EnvironmentContext(EnvironmentReference):
    name: ShortText
    description: str = Field(default="", max_length=3000)
    capabilities: list[ShortText] = Field(default_factory=list, max_length=100)
    skills: list[EnvironmentSkill] = Field(default_factory=list, max_length=100)


class AgentNodeContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ShortText
    description: str = Field(default="", max_length=12000)
    instruction: str = Field(default="", max_length=60000)
    model: str = Field(default="", max_length=300)
    type: str = Field(default="", max_length=100)
    id: str = Field(default="", max_length=300)
    parentId: str = Field(default="", max_length=300)
    path: list[ShortText] = Field(default_factory=list, max_length=32)
    children: list[ShortText] = Field(default_factory=list, max_length=100)
    tools: list[ShortText] = Field(default_factory=list, max_length=100)
    skills: list[ShortText] = Field(default_factory=list, max_length=100)
    subAgents: list[ShortText] = Field(default_factory=list, max_length=100)
    toolDetails: list[CapabilityContext] = Field(default_factory=list, max_length=100)
    skillDetails: list[SkillContext] = Field(default_factory=list, max_length=100)
    components: list[ComponentContext] = Field(default_factory=list, max_length=100)
    searchSources: list[ShortText] = Field(default_factory=list, max_length=100)
    configuration: list[ConfigurationEntry] = Field(default_factory=list, max_length=50)
    mcpServers: list[McpServerContext] = Field(default_factory=list, max_length=100)
    configuredWorkflow: WorkflowContext | None = None
    environment: EnvironmentReference | None = None


class AgentContext(AgentNodeContext):
    metadataSource: Literal["runtime", "draft"] = "draft"
    subAgentDetails: list[AgentNodeContext] = Field(
        default_factory=list, max_length=100
    )
    environments: list[EnvironmentContext] = Field(default_factory=list, max_length=100)
    contextNotes: list[Text] = Field(default_factory=list, max_length=500)


class QualityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: AgentContext
    runtimeId: str = Field(default="", max_length=200)
    region: str = Field(default="", max_length=100)
    language: Literal["zh-CN", "en-US"] = "zh-CN"


class EvaluationBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preference: Preference
    scenario: Text
    requirements: Text


class EvaluationPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ShortText
    goal: Text
    scenarios: Text
    successCriteria: Text
    unacceptableErrors: str = Field(default="", max_length=6000)
    preference: Preference


class PreferenceSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=18)
    ]
    text: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=240, pattern=r"^[^\r\n]+$"
        ),
    ]


class PreferenceSuggestions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestions: list[PreferenceSuggestion] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def distinct_suggestions(self) -> "PreferenceSuggestions":
        items = self.suggestions
        if len({item.label.casefold() for item in items}) != len(items) or len(
            {item.text.casefold() for item in items}
        ) != len(items):
            raise ValueError("Suggestions must be distinct")
        return self


class DatasetPreferences(EvaluationBrief):
    count: int = Field(default=100, ge=50, le=300, strict=True)


class EvaluatorPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overallFocus: Text
    toolsFocus: Text
    skillsFocus: Text
    criteria: Text
    strictness: Literal["lenient", "balanced", "strict"]


class ComponentPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: DatasetPreferences
    evaluators: EvaluatorPreferences


class PreferencesRequest(QualityRequest):
    overallPreferences: EvaluationPreferences


class ComponentGenerationRequest(QualityRequest):
    overallPreferences: EvaluationPreferences | None = None
    componentPreferences: ComponentPreferences | None = None


class PreferenceSuggestionsRequest(ComponentGenerationRequest):
    field: Literal[
        "goal",
        "scenarios",
        "successCriteria",
        "unacceptableErrors",
        "datasetScenarios",
        "datasetRequirements",
        "overallFocus",
        "toolsFocus",
        "skillsFocus",
        "criteria",
    ]

    @model_validator(mode="after")
    def require_component_context(self) -> "PreferenceSuggestionsRequest":
        if self.field not in (
            "goal",
            "scenarios",
            "successCriteria",
            "unacceptableErrors",
        ) and (self.overallPreferences is None or self.componentPreferences is None):
            raise ValueError(
                "Component suggestions require overall and component preferences"
            )
        return self


class GenerateRequest(ComponentGenerationRequest, DatasetPreferences):
    @model_validator(mode="after")
    def validate_preferences(self) -> "GenerateRequest":
        if self.componentPreferences:
            for field in ("preference", "scenario", "requirements", "count"):
                if getattr(self, field) != getattr(
                    self.componentPreferences.dataset, field
                ):
                    raise ValueError(
                        f"{field} must match the reviewed dataset preferences"
                    )
        return self


class EvaluationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ShortText
    scenario: Text
    input: Text
    expectedOutput: Text
    trajectory: list[Text] = Field(max_length=12)
    checks: list[Text] = Field(min_length=1, max_length=12)


class DatasetBatchRequest(GenerateRequest):
    batchStart: int = Field(ge=0, le=299)
    batchCount: int = Field(ge=1, le=20)


class GeneratedDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ShortText
    description: Text
    items: list[EvaluationItem] = Field(min_length=50, max_length=300)


class GeneratedDatasetBatch(GeneratedDataset):
    items: list[EvaluationItem] = Field(min_length=1, max_length=20)


class EvaluationDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Generate the source requirement before naming and scoring the dimension.
    rationale: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1600)
    ] = Field(
        description=(
            "Why this dimension is needed: identify the supplied Agent information "
            "(instruction, description, named tool/Skill description or sub-Agent role), "
            "quote or faithfully summarize the specific requirement, and explain how "
            "it justifies this dimension, in plain language a product developer can "
            "understand. Say what to check and why, without phrases such as failure "
            "scenario or invalid response generation. Distinct from the scoring basis. "
            "Explicitly state missing information instead of inventing capabilities."
        )
    )
    name: ShortText = Field(
        description=(
            "Concise, human-readable dimension title in the requested language. "
            "For zh-CN use a Simplified Chinese title naming the Agent-specific "
            "requirement being checked, not an English name or machine identifier. "
            "Keep tool/Skill identifiers in the rationale, outside the Chinese title."
        )
    )
    description: ShortText
    basis: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1200)
    ] = Field(
        description=(
            "Score ONE case using its applicable requirement from rationale. Give "
            "concrete observable 0/3/5 anchors and state when a check does not apply. "
            "For classification, score choosing the correct outcome for THIS case; "
            "never score how many possible outcome categories appear in one answer. "
            "If metadata is missing, explain the null-score condition instead."
        )
    )
    minScore: float = Field(strict=True, allow_inf_nan=False)
    maxScore: float = Field(strict=True, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_score_range(self) -> "EvaluationDimension":
        if self.minScore >= self.maxScore:
            raise ValueError("minScore must be less than maxScore")
        return self


class EvaluatorDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ShortText
    description: ShortText
    dimensions: list[EvaluationDimension] = Field(min_length=1, max_length=5)
    prompt: Text = Field(
        description=(
            "Standalone evaluator system prompt grounded in this Agent's actual role, "
            "system instructions, node ownership and relevant tools/Skills/knowledge bases. "
            "Include concrete source requirements from the dimension rationales, the exact "
            "dimension names, score anchors and applicability rules; do not return just "
            "a generic scoring template. Use clear, accessible language."
        )
    )


class GeneratedEvaluators(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall: EvaluatorDefinition
    tools: EvaluatorDefinition
    skills: EvaluatorDefinition
