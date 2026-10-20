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

"""Configuration for the DSH runtime."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class DeepSeekHarnessRuntimeConfig(BaseModel):
    """Runtime controls for ``Agent(runtime="dsh")``."""

    provider: str = "deepseek-official"
    model: str | None = None
    reasoning_effort: str | None = None
    max_tokens: int | None = Field(default=None, gt=0)
    cwd: str | None = None
    runtime_cwd: str | None = None
    dsh_bin: str | None = None
    profile: str = "sdk-minimal"
    patches: tuple[str, ...] = ()
    dsh_home: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    initialize_timeout_seconds: float = Field(default=30.0, gt=0)
    request_timeout_seconds: float | None = Field(default=None, gt=0)
    shutdown_timeout_seconds: float | None = Field(default=1.0, gt=0)
    base_url: str | None = None
    api_key: str | None = None

    @field_validator("provider", mode="before")
    @classmethod
    def _normalize_provider(cls, value: Any) -> str:
        if value is None:
            return "deepseek-official"
        text = str(value).strip()
        return text or "deepseek-official"

    @field_validator("cwd", "runtime_cwd", "dsh_bin", "dsh_home", mode="after")
    @classmethod
    def _normalize_path(cls, value: str | None) -> str | None:
        if not value:
            return None
        return str(Path(value).expanduser().resolve())

    @field_validator("patches", mode="before")
    @classmethod
    def _normalize_patches(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            items = (value,)
        else:
            items = tuple(value)
        return tuple(str(Path(item).expanduser().resolve()) for item in items if item)

    @classmethod
    def from_agent(cls, agent: object) -> DeepSeekHarnessRuntimeConfig:
        """Resolve config from the Agent field with narrow environment fallbacks."""
        configured = getattr(agent, "deepseek_harness_runtime_config", None)
        if isinstance(configured, cls):
            config = configured.model_copy(deep=True)
        elif isinstance(configured, dict):
            config = cls.model_validate(configured)
        else:
            config = cls()

        updates: dict[str, object] = {}
        _env_str(updates, "provider", "VEADK_DEEPSEEK_HARNESS_PROVIDER")
        _env_str(updates, "model", "VEADK_DEEPSEEK_HARNESS_MODEL")
        _env_str(
            updates,
            "reasoning_effort",
            "VEADK_DEEPSEEK_HARNESS_REASONING_EFFORT",
        )
        _env_int(updates, "max_tokens", "VEADK_DEEPSEEK_HARNESS_MAX_TOKENS")
        _env_str(updates, "cwd", "VEADK_DEEPSEEK_HARNESS_CWD")
        _env_str(updates, "runtime_cwd", "VEADK_DEEPSEEK_HARNESS_RUNTIME_CWD")
        _env_str(updates, "dsh_bin", "VEADK_DEEPSEEK_HARNESS_DSH_BIN")
        _env_str(updates, "profile", "VEADK_DEEPSEEK_HARNESS_PROFILE")
        _env_str(updates, "dsh_home", "VEADK_DEEPSEEK_HARNESS_DSH_HOME")
        _env_float(
            updates,
            "initialize_timeout_seconds",
            "VEADK_DEEPSEEK_HARNESS_INITIALIZE_TIMEOUT_SECONDS",
        )
        _env_float(
            updates,
            "request_timeout_seconds",
            "VEADK_DEEPSEEK_HARNESS_REQUEST_TIMEOUT_SECONDS",
        )
        _env_float(
            updates,
            "shutdown_timeout_seconds",
            "VEADK_DEEPSEEK_HARNESS_SHUTDOWN_TIMEOUT_SECONDS",
        )
        _env_str(updates, "base_url", "VEADK_DEEPSEEK_HARNESS_BASE_URL")
        _env_str(updates, "api_key", "VEADK_DEEPSEEK_HARNESS_API_KEY")

        return (
            cls.model_validate({**config.model_dump(), **updates})
            if updates
            else config
        )


def _env_str(updates: dict[str, object], field: str, env_name: str) -> None:
    value = os.getenv(env_name)
    if value is not None and value.strip():
        updates[field] = value.strip()


def _env_int(updates: dict[str, object], field: str, env_name: str) -> None:
    value = os.getenv(env_name)
    if value is not None and value.strip():
        updates[field] = int(value)


def _env_float(updates: dict[str, object], field: str, env_name: str) -> None:
    value = os.getenv(env_name)
    if value is not None and value.strip():
        updates[field] = float(value)
