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

"""Configuration for the VeADK Codex runtime."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_KEY_ENV = "VEADK_CODEX_API_KEY"
_SENSITIVE_ENV_MARKERS = (
    "ACCESS_KEY",
    "API_KEY",
    "AUTH",
    "COOKIE",
    "CREDENTIAL",
    "PASSWORD",
    "PRIVATE_KEY",
    "SECRET",
    "TOKEN",
)


class CodexRuntimeConfig(BaseModel):
    """Security and execution controls for ``Agent(runtime="codex")``.

    Defaults are intentionally suitable for a multi-tenant service: Codex may
    write only inside a session-isolated workspace, escalated operations are
    denied, and network access is disabled. Applications that need broader
    access must opt in explicitly.
    """

    approval_mode: Literal["deny_all", "auto_review"] = "deny_all"
    sandbox: Literal["read_only", "workspace_write", "full_access"] = "workspace_write"
    network_access: bool = False
    workspace_root: str | None = None
    reuse_workspace: bool = False
    reasoning_effort: Literal["minimal", "low", "medium", "high", "xhigh"] = "medium"
    personality: Literal["none", "friendly", "pragmatic"] = "pragmatic"
    max_tool_iterations: int = Field(default=8, ge=1, le=64)
    tool_timeout_seconds: float | None = Field(default=120.0, gt=0)

    @field_validator("workspace_root")
    @classmethod
    def _normalize_workspace_root(cls, value: str | None) -> str | None:
        if not value:
            return None
        return str(Path(value).expanduser().resolve())

    @classmethod
    def from_agent(cls, agent: object) -> "CodexRuntimeConfig":
        """Resolve config from the Agent field with narrow environment fallbacks."""
        configured = getattr(agent, "codex_runtime_config", None)
        if isinstance(configured, cls):
            config = configured.model_copy(deep=True)
        elif isinstance(configured, dict):
            config = cls.model_validate(configured)
        else:
            config = cls()

        # Environment fallbacks keep existing deployments configurable without
        # widening the generic model_extra_config surface.
        updates: dict[str, object] = {}
        if value := os.getenv("VEADK_CODEX_SANDBOX"):
            updates["sandbox"] = value
        if value := os.getenv("VEADK_CODEX_APPROVAL_MODE"):
            updates["approval_mode"] = value
        if value := os.getenv("VEADK_CODEX_WORKSPACE_ROOT"):
            updates["workspace_root"] = value
        if value := os.getenv("VEADK_CODEX_NETWORK_ACCESS"):
            updates["network_access"] = value.strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        return (
            cls.model_validate({**config.model_dump(), **updates})
            if updates
            else config
        )


def codex_subprocess_env(codex_home: str, turn_token: str) -> dict[str, str]:
    """Mask host credentials inherited by the SDK's subprocess launcher."""
    overrides = {
        name: ""
        for name in os.environ
        if any(marker in name.upper() for marker in _SENSITIVE_ENV_MARKERS)
    }
    overrides.update({"CODEX_HOME": codex_home, _KEY_ENV: turn_token})
    return overrides


def toml_string(value: str) -> str:
    """Encode an untrusted value as a TOML-compatible basic string."""
    return json.dumps(value, ensure_ascii=False)
