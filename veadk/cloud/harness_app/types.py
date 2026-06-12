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
from veadk.prompts.agent_default_prompt import DEFAULT_INSTRUCTION


class HarnessOverrides(BaseModel):
    """Harness parameters that may be overridden on a per-invocation basis.

    Field descriptions are the single source of truth for both the FastAPI schema
    and the ``veadk harness invoke`` CLI flags (which are generated from these
    fields), so adding a field here exposes a new override everywhere.
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


class HarnessConfig(HarnessOverrides):
    """Full harness parameters fixed when the agent is created.

    Extends :class:`HarnessOverrides` with the knowledge base and memory
    backends. These are wired into the agent at build time and cannot be changed
    per request, so they are intentionally absent from :class:`HarnessOverrides`.

    An empty backend string means the component is disabled (not created).
    """

    app_name: str = Field(default="harness_app", alias="name")
    system_prompt: str = Field(default=DEFAULT_INSTRUCTION)
    knowledgebase_type: str = Field(default="")
    longterm_memory_type: str = Field(default="")
    shortterm_memory_type: str = Field(default="local")
    runtime: Literal["adk", "codex"] = Field(default="adk")


class RunAgentRequest(BaseModel):
    user_id: str
    session_id: str


class InvokeHarnessRequest(BaseModel):
    prompt: str
    harness_name: str
    # When present, a once-time override applied on top of the served agent for
    # this single call. Only the fields actually set are applied; memory and the
    # knowledge base are never overridable (absent from HarnessOverrides).
    harness: HarnessOverrides | None = None
    run_agent_request: RunAgentRequest


class InvokeHarnessResponse(BaseModel):
    harness_name: str
    overwrite: bool = Field(default=False)
    output: str
