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

"""VeADK-managed lifecycle for the AgentKit Harness Sidecar product API."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping, MutableMapping
from typing import Any

logger = logging.getLogger(__name__)

_INSTALL_HINT = 'pip install "veadk-python[harness-sidecar]"'


class HarnessSidecarDependencyError(RuntimeError):
    """Raised when Sidecar was requested without its optional dependency."""


class ManagedHarnessSidecar:
    """Own one Sidecar binding without exposing process details to VeADK users."""

    def __init__(
        self,
        config: bool | Mapping[str, Any] | Any = False,
        *,
        profile: str = "default",
        process_env: Mapping[str, str] | None = None,
        binding_env: MutableMapping[str, str] | None = None,
    ) -> None:
        self.config = config
        self.profile = profile
        self.process_env = process_env
        self.binding_env = binding_env if binding_env is not None else os.environ
        self.binding: Any | None = None
        self.error: Exception | None = None
        self._attempted = False
        self.plan = resolve_sidecar_plan(config, profile=profile)

    @property
    def enabled(self) -> bool:
        if isinstance(self.config, bool):
            return self.config
        if isinstance(self.config, Mapping):
            return bool(self.config.get("enabled", True))
        return bool(getattr(self.config, "enabled", True))

    @property
    def fail_open(self) -> bool:
        if isinstance(self.config, Mapping):
            return bool(self.config.get("fail_open", True))
        return bool(getattr(self.config, "fail_open", True))

    @property
    def status(self) -> str:
        if self.binding is not None:
            return str(self.binding.spec.status)
        if self.error is not None:
            return "degraded"
        return "not_started" if self.enabled else "disabled"

    @property
    def env(self) -> dict[str, str]:
        return dict(self.binding.env) if self.binding is not None else {}

    def start(self) -> Any | None:
        if not self.enabled or self.binding is not None or self._attempted:
            return self.binding
        self._attempted = True
        try:
            start_harness_sidecar = _public_start_function()
            self.binding = start_harness_sidecar(
                self.config,
                profile=self.profile,
                apply_env=True,
                environ=self.binding_env,
                process_env=self.process_env,
            )
        except Exception as error:
            self.error = error
            if not self.fail_open:
                raise
            logger.warning("Harness Sidecar startup failed open: %s", error)
        return self.binding

    def close(self) -> None:
        if self.binding is not None:
            self.binding.stop()
            self.binding = None


def sidecar_config_from_env(env: Mapping[str, str] | None = None) -> Any | bool:
    """Load the public AgentKit Sidecar config only when explicitly enabled."""

    values = env if env is not None else os.environ
    if not _truthy(values.get("HARNESS_SIDECAR_ENABLED")):
        return False
    try:
        from agentkit.toolkit.harness import HarnessSidecarConfig
    except (ImportError, AttributeError) as error:
        raise HarnessSidecarDependencyError(
            f"Harness Sidecar support is not installed. Install it with: {_INSTALL_HINT}"
        ) from error
    return HarnessSidecarConfig.from_env(values)


def normalize_sidecar_config(value: Any | None) -> bool | dict[str, Any]:
    """Convert public config objects into VeADK's serializable extension config."""

    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return dict(model_dump(exclude_none=True))
    raise TypeError("sidecar must be a bool, mapping, or HarnessSidecarConfig")


def resolve_sidecar_plan(
    value: bool | Mapping[str, Any] | Any,
    *,
    profile: str,
) -> Any | None:
    """Resolve the public Product Component plan without starting the Runtime."""

    enabled = (
        value
        if isinstance(value, bool)
        else bool(
            value.get("enabled", True)
            if isinstance(value, Mapping)
            else getattr(value, "enabled", True)
        )
    )
    if not enabled:
        return None
    try:
        from agentkit.toolkit.harness import resolve_sidecar_config
    except (ImportError, AttributeError) as error:
        raise HarnessSidecarDependencyError(
            f"Harness Sidecar support is not installed. Install it with: {_INSTALL_HINT}"
        ) from error
    config = resolve_sidecar_config(value, profile=profile)
    plan = config.resolved_plan
    if not plan.valid:
        raise ValueError("; ".join(plan.errors))
    return plan


def _public_start_function():
    try:
        from agentkit.toolkit.harness import start_harness_sidecar
    except (ImportError, AttributeError) as error:
        raise HarnessSidecarDependencyError(
            f"Harness Sidecar support is not installed. Install it with: {_INSTALL_HINT}"
        ) from error
    return start_harness_sidecar


def _truthy(value: str | None) -> bool:
    return bool(value and value.strip().lower() in {"1", "true", "yes", "on"})


__all__ = [
    "HarnessSidecarDependencyError",
    "ManagedHarnessSidecar",
    "normalize_sidecar_config",
    "resolve_sidecar_plan",
    "sidecar_config_from_env",
]
