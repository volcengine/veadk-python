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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from veadk.agent import Agent

_PROVIDER_ID = "veadk"
_MODEL_API = "openai-completions"
_MODEL_KEY_ENV = "VEADK_PI_MODEL_API_KEY"


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
    disable_tools: bool = True
    disable_builtin_tools: bool = False
    extensions: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    disable_skill_discovery: bool = True
    skill_paths: tuple[str, ...] = ()

    @classmethod
    def from_agent(cls, agent: "Agent", binary_path: str) -> "PiAgentConfig":
        agent_dir = os.getenv("PIAGENT_AGENT_DIR") or os.getenv("PI_CODING_AGENT_DIR")
        if agent_dir:
            resolved_agent_dir = Path(agent_dir).expanduser()
        else:
            resolved_agent_dir = Path(tempfile.mkdtemp(prefix="veadk-piagent-"))

        workdir = Path(os.getenv("PIAGENT_WORKDIR", os.getcwd())).expanduser()
        timeout = float(os.getenv("PIAGENT_TIMEOUT_SECONDS", "600"))

        return cls(
            binary_path=binary_path,
            agent_dir=resolved_agent_dir,
            workdir=workdir,
            timeout_seconds=timeout,
            model=PiAgentModelConfig.from_agent(agent),
            disable_tools=_env_flag_enabled("PIAGENT_DISABLE_TOOLS", default=True),
            disable_skill_discovery=_env_flag_enabled(
                "PIAGENT_DISABLE_SKILL_DISCOVERY", default=True
            ),
        )

    def with_tools(
        self, *, extensions: list[str], allowed_tools: list[str]
    ) -> "PiAgentConfig":
        return replace(
            self,
            disable_tools=False,
            disable_builtin_tools=True,
            extensions=tuple(extensions),
            allowed_tools=tuple(allowed_tools),
        )

    def with_skills(self, *, skill_paths: list[str]) -> "PiAgentConfig":
        return replace(
            self,
            disable_skill_discovery=True,
            skill_paths=tuple(skill_paths),
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


def prepare_piagent_home(config: PiAgentConfig) -> None:
    """Create Pi's isolated agent directory and write custom model config."""

    config.agent_dir.mkdir(parents=True, exist_ok=True)
    config.sessions_dir.mkdir(parents=True, exist_ok=True)
    payload = config.model.to_models_json()
    config.models_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
