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

"""Configuration for the optional decision model."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, Field, field_validator

DEFAULT_API_BASE = "https://api.typesafe.ai"
OPENROUTER_API_BASE = "https://openrouter.ai/api"
DEFAULT_MODEL_NAME = "jev-latest"
SYSTEM_ONE_PATH = "/v1/systemone"

ENV_PREFIX = "DECISION_MODEL_"
# ``config.yaml`` is flattened into environment variables, so ``model.decision``
# arrives as ``MODEL_DECISION_*``. Both spellings are accepted; the explicit
# ``DECISION_MODEL_*`` variable wins when both are set.
CONFIG_YAML_PREFIX = "MODEL_DECISION_"

# Every deployment speaks the same System One protocol, so switching provider
# only changes the API base and the API key. "typesafe" is the hosted service,
# "openrouter" forwards System One to the same model, and "systemone" is a
# self-hosted server -- which has no public default and therefore must set
# ``api_base`` explicitly.
DecisionProvider = Literal["typesafe", "openrouter", "systemone"]

DEFAULT_API_BASE_BY_PROVIDER: dict[DecisionProvider, str] = {
    "typesafe": DEFAULT_API_BASE,
    "openrouter": OPENROUTER_API_BASE,
    "systemone": DEFAULT_API_BASE,
}


class DecisionModelConfig(BaseModel):
    """Connection settings for a decision model.

    The decision model is optional and independent from the agent model. When
    it is disabled or missing an API key, every caller must keep working
    without it.
    """

    enabled: bool = False
    provider: DecisionProvider = "typesafe"
    name: str = DEFAULT_MODEL_NAME
    api_base: str = DEFAULT_API_BASE
    api_key: str = ""
    timeout: float = Field(default=30.0, gt=0)
    max_retries: int = Field(default=3, ge=0)

    @field_validator("api_base")
    @classmethod
    def _normalize_api_base(cls, value: str) -> str:
        """Strip a trailing slash and reject an empty API base."""
        base = value.strip().rstrip("/")
        if not base:
            raise ValueError("api_base must not be empty")
        return base

    @property
    def endpoint(self) -> str:
        """Return the full evaluation endpoint for this deployment."""
        if self.api_base.endswith(SYSTEM_ONE_PATH):
            return self.api_base
        return self.api_base + SYSTEM_ONE_PATH

    @property
    def configured(self) -> bool:
        """Whether the decision model is usable as configured."""
        return bool(self.enabled and self.api_key)

    @classmethod
    def disabled(cls) -> DecisionModelConfig:
        """Return the default disabled configuration."""
        return cls()

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> DecisionModelConfig:
        """Build a configuration from ``DECISION_MODEL_*`` variables.

        Args:
            env: Mapping to read instead of ``os.environ`` (used by tests).

        Returns:
            The parsed configuration; disabled when nothing is configured.
        """
        values = env if env is not None else os.environ
        provider = _env_provider(_lookup(values, "PROVIDER"))
        return cls(
            enabled=_env_bool(_lookup(values, "ENABLED")),
            provider=provider,
            name=_lookup(values, "NAME") or DEFAULT_MODEL_NAME,
            api_base=(
                _lookup(values, "API_BASE") or DEFAULT_API_BASE_BY_PROVIDER[provider]
            ),
            api_key=_lookup(values, "API_KEY") or "",
            timeout=_env_float(_lookup(values, "TIMEOUT"), 30.0),
            max_retries=_env_int(_lookup(values, "MAX_RETRIES"), 3),
        )


def _lookup(values: Mapping[str, str], name: str) -> str | None:
    """Read one setting from either accepted environment spelling."""
    for prefix in (ENV_PREFIX, CONFIG_YAML_PREFIX):
        value = values.get(f"{prefix}{name}")
        if value not in (None, ""):
            return str(value)
    return None


def _env_bool(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _env_provider(raw: str | None) -> DecisionProvider:
    value = (raw or "").strip().lower()
    if value in ("typesafe", "openrouter", "systemone"):
        return value  # type: ignore[return-value]
    return "typesafe"


def _env_float(raw: str | None, default: float) -> float:
    try:
        return float(raw) if raw not in (None, "") else default
    except ValueError:
        return default


def _env_int(raw: str | None, default: int) -> int:
    try:
        return int(raw) if raw not in (None, "") else default
    except ValueError:
        return default
