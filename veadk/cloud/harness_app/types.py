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

"""Harness parameter schemas for the deployable harness app.

The parameters split into two groups:

* :class:`HarnessOverrides` — the subset that may be overridden per invocation
  (model, prompt, tools, skills, runtime).
* :class:`HarnessConfig` — the full set fixed at agent creation time. It extends
  the overridable params with the knowledge base and memory components, which are
  bound when the agent is built and therefore **cannot** be overridden per request.

``tools`` and ``skills`` are comma-separated strings (e.g. ``"web_search,web_fetch"``).
"""

from typing import Literal

from pydantic import BaseModel, Field

from veadk.consts import DEFAULT_MODEL_AGENT_NAME
from veadk.prompts.agent_default_prompt import DEFAULT_DESCRIPTION, DEFAULT_INSTRUCTION


class HarnessOverrides(BaseModel):
    """Harness parameters that may be overridden on a per-invocation basis.

    Field descriptions are the source of truth for the FastAPI schema and most
    ``veadk harness invoke`` CLI flags. ``registry_*`` fields are accepted for
    AgentKit's harness invoke API but intentionally hidden from the VeADK CLI.
    """

    model_name: str = Field(
        default=DEFAULT_MODEL_AGENT_NAME, description="Reasoning model name."
    )
    tools: str = Field(
        default="",
        description="Comma-separated built-in tool names, e.g. web_search,web_fetch.",
    )
    skills: str = Field(default="", description="Comma-separated skill hub names.")
    system_prompt: str = Field(
        default="You are a helpful assistant.",
        description="System prompt / instruction.",
    )
    runtime: Literal["adk", "codex"] = Field(
        default="adk", description="Agent runtime backend."
    )
    registry_space_id: str = Field(
        default="", description="Override the AgentKit A2A registry space id."
    )
    registry_endpoint: str = Field(
        default="", description="Override the AgentKit A2A registry OpenAPI endpoint."
    )
    registry_region: str = Field(
        default="", description="Override the AgentKit A2A registry OpenAPI region."
    )
    registry_top_k: int = Field(
        default=3, description="Override the number of A2A AgentCards to retrieve."
    )


class HarnessConfig(HarnessOverrides):
    """Full harness parameters fixed when the agent is created.

    Extends :class:`HarnessOverrides` with the knowledge base and memory
    backends. These are wired into the agent at build time and cannot be changed
    per request, so they are intentionally absent from :class:`HarnessOverrides`.

    An empty backend string means the component is disabled (not created).
    """

    app_name: str = Field(default="harness_app", alias="name")
    system_prompt: str = Field(default=DEFAULT_INSTRUCTION)
    description: str = Field(default=DEFAULT_DESCRIPTION)
    knowledgebase_type: str = Field(default="")
    longterm_memory_type: str = Field(default="")
    shortterm_memory_type: str = Field(default="local")
    runtime: Literal["adk", "codex"] = Field(default="adk")
    max_llm_calls: int | None = Field(
        default=None,
        description="Default max LLM calls per run; unset follows ADK RunConfig's default. Overridable per invocation.",
    )
    structured_tool_calls: bool = Field(default=False)
    include_tools_every_turn: bool = Field(default=True)
    registry_type: Literal["", "agentkit_a2a"] = Field(default="")
    registry_version: str = Field(default="")
    registry_service_name: str = Field(default="")
    registry_timeout_ms: int = Field(default=60000)
    registry_poll_interval_ms: int = Field(default=5000)


class HarnessEnhanceOverrides(BaseModel):
    """Per-invocation Harness enhancement options.

    This mirrors the runtime ``harness_enhance`` section but is intentionally
    small: callers can enable the plugin bundle, choose components, select a
    profile, and choose the compaction provider. Runtime limits keep their
    deploy-time defaults.
    """

    enabled: bool = Field(
        default=False,
        description="Enable Harness plugins for this single invocation.",
    )
    components: str = Field(
        default="invocation_context,compactor,response_verification",
        description="Comma-separated Harness plugin components.",
    )
    profile: str = Field(default="default", description="Harness profile name.")
    compression_provider: str | None = Field(
        default=None,
        description="Tool-result compaction provider, e.g. builtin or headroom.",
    )


class RunAgentRequest(BaseModel):
    user_id: str
    session_id: str
    max_llm_calls: int | None = Field(
        default=None,
        description="Override max LLM calls for this single call (falls back to the harness default, then ADK's).",
    )


class LlmUsageMetrics(BaseModel):
    """Aggregated model usage for one HarnessApp invocation."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    usage_event_count: int = 0

    def add(self, value: "LlmUsageMetrics") -> None:
        self.prompt_tokens += value.prompt_tokens
        self.completion_tokens += value.completion_tokens
        self.total_tokens += value.total_tokens
        self.cached_tokens += value.cached_tokens
        self.usage_event_count += value.usage_event_count

    def has_tokens(self) -> bool:
        return bool(self.total_tokens or self.prompt_tokens or self.completion_tokens)


class HarnessCompactionMetric(BaseModel):
    """Compaction accounting exposed by HarnessApp diagnostics."""

    provider: str = ""
    original_chars: int = 0
    compressed_chars: int = 0
    changed: bool = False
    tokens_before: int = 0
    tokens_after: int = 0
    tokens_saved: int = 0
    compression_ratio: float = 0.0
    transforms_applied: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class HarnessPluginMetrics(BaseModel):
    """Harness plugin diagnostics for one invocation."""

    names: list[str] = Field(default_factory=list)
    compaction_reports: list[HarnessCompactionMetric] = Field(default_factory=list)


class HarnessResponseMetrics(BaseModel):
    """Optional machine-readable metrics returned by HarnessApp Runtime."""

    llm_usage: LlmUsageMetrics = Field(default_factory=LlmUsageMetrics)
    harness_plugins: HarnessPluginMetrics = Field(default_factory=HarnessPluginMetrics)


class InvokeHarnessRequest(BaseModel):
    prompt: str
    harness_name: str
    # When present, a once-time override applied on top of the served agent for
    # this single call. Only the fields actually set are applied; memory and the
    # knowledge base are never overridable (absent from HarnessOverrides).
    harness: HarnessOverrides | None = None
    harness_enhance: HarnessEnhanceOverrides | None = None
    run_agent_request: RunAgentRequest


class InvokeHarnessResponse(BaseModel):
    harness_name: str
    overwrite: bool = Field(default=False)
    output: str
    metrics: HarnessResponseMetrics | None = Field(
        default=None,
        description="Optional runtime metrics, enabled by HARNESS_APP_RETURN_LLM_USAGE.",
    )
    error: str | None = Field(
        default=None,
        description=(
            "Error message when the invocation fails (unsupported tool, skill "
            "load failure, or a runtime error). Passed through verbatim; `output` "
            "is empty when set."
        ),
    )
