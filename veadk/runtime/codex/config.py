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

from pydantic import BaseModel, Field, field_validator, model_validator

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

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

    Security note on ``approval_mode``: ``"auto_review"`` is **not** a review
    gate. The Codex SDK's built-in approval handler answers every
    ``requestApproval`` notification with ``accept``, and ``AsyncCodex`` exposes
    no hook to replace it, so ``"auto_review"`` auto-approves every sandbox
    escalation and file change without consulting a human or ADK. Only
    ``"deny_all"`` (the default) actually keeps Codex inside the sandbox.

    Security note on ``network_access``: it is written to the
    ``[sandbox_workspace_write]`` table of Codex's ``config.toml`` and is read
    only by the ``workspace-write`` sandbox. The ``read-only`` and
    ``danger-full-access`` sandboxes ignore it entirely, so it cannot restrict
    (or grant) network access outside ``sandbox="workspace_write"``.
    """

    approval_mode: Literal["deny_all", "auto_review"] = Field(
        default="deny_all",
        description=(
            "'deny_all' refuses every escalation Codex requests. 'auto_review' "
            "AUTO-APPROVES them: the SDK's default approval handler accepts "
            "every command-execution and file-change approval request, and no "
            "human or ADK confirmation is consulted. Treat 'auto_review' as "
            "full auto-approval, not as a review step."
        ),
    )
    sandbox: Literal["read_only", "workspace_write", "full_access"] = "workspace_write"
    network_access: bool = Field(
        default=False,
        description=(
            "Allow network access from the sandbox. Only honoured by "
            "sandbox='workspace_write'; 'read_only' and 'full_access' ignore it."
        ),
    )
    workspace_root: str | None = None
    reuse_workspace: bool = False
    reasoning_effort: Literal["minimal", "low", "medium", "high", "xhigh"] = "medium"
    personality: Literal["none", "friendly", "pragmatic"] = "pragmatic"
    max_tool_iterations: int = Field(
        default=32,
        ge=1,
        le=256,
        description=(
            "ADK tool round-trips the shim may run for the whole Codex turn. "
            "This budget is per turn, not per backend request: Codex issues one "
            "request per native tool round, so a per-request counter allowed "
            "rounds x budget executions. The default is higher than the old "
            "per-request value so that turns which use an ADK tool after "
            "several native tool rounds are not cut short."
        ),
    )
    tool_timeout_seconds: float | None = Field(default=120.0, gt=0)

    @field_validator("workspace_root")
    @classmethod
    def _normalize_workspace_root(cls, value: str | None) -> str | None:
        if not value:
            return None
        return str(Path(value).expanduser().resolve())

    @model_validator(mode="after")
    def _check_sandbox_network_consistency(self) -> "CodexRuntimeConfig":
        """Reject sandbox/network combinations that misstate the isolation.

        ``network_access`` only reaches Codex through the
        ``[sandbox_workspace_write]`` table, which ``danger-full-access`` and
        ``read-only`` ignore. Silently accepting those combinations lets a
        config read as "no network" while granting full network, so the
        dangerous direction raises and the harmless one warns.

        Returns:
            CodexRuntimeConfig: The validated config.

        Raises:
            ValueError: If ``sandbox="full_access"`` is combined with
                ``network_access=False``.
        """
        if self.sandbox == "full_access" and not self.network_access:
            raise ValueError(
                "CodexRuntimeConfig(sandbox='full_access') ignores "
                "network_access, so network_access=False gives no network "
                "isolation. Set sandbox='workspace_write' to actually block "
                "network access, or set network_access=True to acknowledge "
                "the risk."
            )
        if self.sandbox == "read_only" and self.network_access:
            logger.warning(
                "CodexRuntimeConfig(sandbox='read_only') ignores "
                "network_access=True, which only applies to the "
                "workspace_write sandbox. Set sandbox='workspace_write' if "
                "the agent needs network access."
            )
        return self

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
