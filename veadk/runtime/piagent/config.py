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

"""Configuration helpers for the Pi runtime."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

if TYPE_CHECKING:
    from veadk.agent import Agent

_PROVIDER_ID = "veadk"
_MODEL_API = "openai-completions"
_MODEL_KEY_ENV = "VEADK_PI_MODEL_API_KEY"
_REAL_PI_AGENT_DIR = Path.home() / ".pi" / "agent"


@dataclass(frozen=True)
class PiAgentModelConfig:
    """Model/provider config injected into Pi's custom model registry."""

    provider_id: str
    model: str
    base_url: str
    api_key: str
    api: str
    api_key_env: str

    @classmethod
    def from_agent(cls, agent: "Agent") -> "PiAgentModelConfig":
        model_name = agent.model_name
        if isinstance(model_name, list):
            model = model_name[0] if model_name else ""
        else:
            model = model_name

        if not model:
            raise ValueError(
                "piagent runtime requires a model: set Agent(model_name=...)."
            )
        if not agent.model_api_base:
            raise ValueError(
                "piagent runtime requires model_api_base for the Pi custom provider."
            )
        if not agent.model_api_key:
            raise ValueError(
                "piagent runtime requires model_api_key for the Pi custom provider."
            )

        return cls(
            provider_id=os.getenv("PIAGENT_PROVIDER_ID", _PROVIDER_ID),
            model=model,
            base_url=agent.model_api_base,
            api_key=agent.model_api_key,
            api=os.getenv("PIAGENT_MODEL_API", _MODEL_API),
            api_key_env=os.getenv("PIAGENT_MODEL_API_KEY_ENV", _MODEL_KEY_ENV),
        )

    def to_models_json(self) -> dict[str, Any]:
        return {
            "providers": {
                self.provider_id: {
                    "name": "VeADK",
                    "baseUrl": self.base_url,
                    "api": self.api,
                    "apiKey": f"${self.api_key_env}",
                    "compat": {
                        "supportsDeveloperRole": False,
                        "supportsReasoningEffort": False,
                    },
                    "models": [
                        {
                            "id": self.model,
                            "name": self.model,
                            "input": ["text"],
                        }
                    ],
                }
            }
        }


@dataclass(frozen=True)
class PiAgentConfig:
    """Resolved runtime config for one Pi invocation."""

    binary_path: str
    agent_dir: Path
    workdir: Path
    timeout_seconds: float
    model: PiAgentModelConfig
    disable_tools: bool = False
    disable_builtin_tools: bool = False
    disable_extension_discovery: bool = True
    extensions: tuple[str, ...] = ()
    tool_allowlist: tuple[str, ...] = ()
    exclude_tools: tuple[str, ...] = ()
    disable_skill_discovery: bool = True
    skill_paths: tuple[str, ...] = ()
    project_trust: Literal["deny", "approve", "default"] = "deny"

    @classmethod
    def from_agent(cls, agent: "Agent", binary_path: str) -> "PiAgentConfig":
        resolved_agent_dir = _resolve_agent_dir()

        workdir = Path(os.getenv("PIAGENT_WORKDIR", os.getcwd())).expanduser()
        timeout = float(os.getenv("PIAGENT_TIMEOUT_SECONDS", "600"))

        return cls(
            binary_path=binary_path,
            agent_dir=resolved_agent_dir,
            workdir=workdir,
            timeout_seconds=timeout,
            model=PiAgentModelConfig.from_agent(agent),
            disable_tools=_env_flag_enabled("PIAGENT_DISABLE_TOOLS", default=False),
            disable_builtin_tools=_env_flag_enabled(
                "PIAGENT_DISABLE_BUILTIN_TOOLS", default=False
            ),
            disable_extension_discovery=_env_discovery_disabled(
                disable_env="PIAGENT_DISABLE_EXTENSION_DISCOVERY",
                enable_env="PIAGENT_ENABLE_EXTENSION_DISCOVERY",
                default_disabled=True,
            ),
            tool_allowlist=_env_csv("PIAGENT_TOOL_ALLOWLIST"),
            exclude_tools=_env_csv("PIAGENT_EXCLUDE_TOOLS"),
            disable_skill_discovery=_env_discovery_disabled(
                disable_env="PIAGENT_DISABLE_SKILL_DISCOVERY",
                enable_env="PIAGENT_ENABLE_SKILL_DISCOVERY",
                default_disabled=True,
            ),
            project_trust=_env_project_trust(),
        )

    def with_tools(self, *, extensions: list[str]) -> "PiAgentConfig":
        return replace(
            self,
            disable_tools=False,
            extensions=tuple([*self.extensions, *extensions]),
        )

    def with_skills(self, *, skill_paths: list[str]) -> "PiAgentConfig":
        return replace(
            self,
            skill_paths=tuple([*self.skill_paths, *skill_paths]),
        )

    @property
    def models_path(self) -> Path:
        return self.agent_dir / "models.json"

    @property
    def sessions_dir(self) -> Path:
        return self.agent_dir / "sessions"


def _env_flag_enabled(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _env_csv(name: str) -> tuple[str, ...]:
    value = os.getenv(name, "")
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _env_discovery_disabled(
    *, disable_env: str, enable_env: str, default_disabled: bool
) -> bool:
    if os.getenv(disable_env) is not None:
        return _env_flag_enabled(disable_env, default=default_disabled)
    if os.getenv(enable_env) is not None:
        return not _env_flag_enabled(enable_env, default=False)
    return default_disabled


def _env_project_trust() -> Literal["deny", "approve", "default"]:
    value = os.getenv("PIAGENT_PROJECT_TRUST", "deny").strip().lower()
    if value not in {"deny", "approve", "default"}:
        raise ValueError(
            "PIAGENT_PROJECT_TRUST must be one of: deny, approve, default."
        )
    return cast(Literal["deny", "approve", "default"], value)


def _resolve_agent_dir() -> Path:
    agent_dir = os.getenv("PIAGENT_AGENT_DIR")
    if agent_dir:
        return _validate_isolated_agent_dir(Path(agent_dir).expanduser())

    if _env_flag_enabled("PIAGENT_ALLOW_PARENT_PI_CODING_AGENT_DIR", default=False):
        parent_dir = os.getenv("PI_CODING_AGENT_DIR")
        if parent_dir:
            return _validate_isolated_agent_dir(Path(parent_dir).expanduser())

    return Path(tempfile.mkdtemp(prefix="veadk-piagent-"))


def _validate_isolated_agent_dir(path: Path) -> Path:
    resolved = path.resolve()
    real_home = _REAL_PI_AGENT_DIR.expanduser().resolve()
    if resolved == real_home or real_home in resolved.parents:
        raise ValueError(
            "piagent runtime requires an isolated PIAGENT_AGENT_DIR; refusing to "
            f"use the real Pi home: {real_home}"
        )
    return resolved


def prepare_piagent_home(config: PiAgentConfig) -> None:
    """Create Pi's isolated agent directory and write custom model config."""

    config.agent_dir.mkdir(parents=True, exist_ok=True)
    config.sessions_dir.mkdir(parents=True, exist_ok=True)
    payload = config.model.to_models_json()
    config.models_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
