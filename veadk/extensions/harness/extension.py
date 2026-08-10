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

"""VeADK extension facade for Harness plugins."""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from typing import Any

from google.adk.plugins import BasePlugin
from pydantic import Field
from typing_extensions import Self

from veadk.extensions.harness.env import (
    build_harness_plugins_from_env,
    harness_enabled_from_env,
)
from veadk.extensions.harness.modules.final_response_verifier import (
    FinalResponseVerifierConfig,
)
from veadk.extensions.harness.modules.invocation_context import (
    HarnessInvocationContextConfig,
)
from veadk.extensions.harness.modules.tool_result_compactor import (
    ToolResultCompactorConfig,
)
from veadk.extensions.harness.plugins import build_harness_plugins
from veadk.extensions.harness.schemas import HarnessBaseModel
from veadk.extensions.harness.sidecar import (
    ManagedHarnessSidecar,
    normalize_sidecar_config,
    sidecar_config_from_env,
)
from veadk.extensions.harness.stores import HarnessStoreProtocol


class HarnessExtensionConfig(HarnessBaseModel):
    """Configuration for :class:`HarnessExtension`."""

    enabled: bool = True
    components: list[str] = Field(
        default_factory=lambda: [
            "invocation_context",
            "compactor",
            "response_verification",
        ]
    )
    profile: str = "default"
    sidecar: bool | dict[str, Any] = False


class HarnessExtension:
    """Small VeADK-facing wrapper for Harness plugin assembly.

    The extension owns no core Harness logic. It keeps the public VeADK entry
    point compact while delegating atomic behavior to the modules in this
    package.
    """

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        components: Iterable[str] | str | None = None,
        profile: str = "default",
        store: HarnessStoreProtocol | None = None,
        context_config: HarnessInvocationContextConfig | None = None,
        compaction_config: ToolResultCompactorConfig | None = None,
        verifier_config: FinalResponseVerifierConfig | None = None,
        sidecar: bool | Mapping[str, Any] | Any | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        normalized_sidecar = normalize_sidecar_config(sidecar)
        self.sidecar = ManagedHarnessSidecar(
            normalized_sidecar,
            profile=profile,
            process_env=dict(env) if env is not None else None,
        )
        if self.sidecar.enabled:
            if components is not None:
                raise ValueError(
                    "components cannot be combined with Harness Sidecar; "
                    "use component_overrides with Product Component IDs"
                )
            plan = self.sidecar.plan
            if plan is None:
                raise RuntimeError("Harness Sidecar enabled without a resolved plan")
            component_list = list(plan.activation_targets.veadk_plugins)
            plugin_enabled = True
        elif components is None:
            component_list = _default_components(profile)
            plugin_enabled = True if enabled is None else enabled
        elif isinstance(components, str):
            component_list = [
                item.strip() for item in components.split(",") if item.strip()
            ]
            plugin_enabled = True if enabled is None else enabled
        else:
            component_list = [
                str(item).strip() for item in components if str(item).strip()
            ]
            plugin_enabled = True if enabled is None else enabled
        self.config = HarnessExtensionConfig(
            enabled=plugin_enabled,
            components=component_list,
            profile=profile,
            sidecar=normalized_sidecar,
        )
        self.store = store
        self.context_config = context_config
        self.compaction_config = compaction_config
        self.verifier_config = verifier_config
        self.env = dict(env) if env is not None else None
        self.sidecar.start()

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> HarnessExtension:
        """Create an extension controlled by Harness environment variables."""

        values = dict(env if env is not None else os.environ)
        return cls(
            enabled=harness_enabled_from_env(values),
            profile=(
                values.get("HARNESS_ENHANCE_PROFILE")
                or values.get("HARNESS_PROFILE")
                or "default"
            ),
            sidecar=sidecar_config_from_env(values),
            env=values,
        )

    def plugins(self) -> list[BasePlugin]:
        """Build plugins for ``Runner(..., plugins=...)``."""

        self.sidecar.start()
        if self.sidecar.enabled:
            return build_harness_plugins(
                components=self.config.components,
                profile=self.config.profile,
                store=self.store,
                context_config=self.context_config,
                compaction_config=self.compaction_config,
                verifier_config=self.verifier_config,
            )
        if self.env is not None:
            return build_harness_plugins_from_env(self.env)
        if not self.config.enabled:
            return []
        return build_harness_plugins(
            components=self.config.components,
            profile=self.config.profile,
            store=self.store,
            context_config=self.context_config,
            compaction_config=self.compaction_config,
            verifier_config=self.verifier_config,
        )

    @property
    def sidecar_status(self) -> str:
        """Return ``ok``, ``degraded``, ``disabled``, or runtime status."""

        return self.sidecar.status

    @property
    def sidecar_env(self) -> dict[str, str]:
        """Return environment bindings injected by the managed Sidecar."""

        return self.sidecar.env

    def sidecar_status_payload(self) -> dict[str, Any]:
        """Return a safe status snapshot suitable for the application route."""

        spec = getattr(self.sidecar.binding, "spec", None)
        effective = list(
            getattr(spec, "effective_components", None)
            or getattr(self.sidecar.plan, "effective_components", None)
            or []
        )
        return {
            "enabled": self.sidecar.enabled,
            "status": self.sidecar_status,
            "planHash": self.sidecar.plan_hash,
            "effectiveComponents": effective,
        }

    def close(self) -> None:
        """Stop the managed Sidecar before the application process exits."""

        self.sidecar.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def _default_components(profile: str) -> list[str]:
    components = HarnessExtensionConfig().components
    if profile == "ops":
        return [*components, "long_run_control"]
    return components


__all__ = ["HarnessExtension", "HarnessExtensionConfig"]
