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

from google.adk.plugins import BasePlugin
from pydantic import Field

from veadk.extensions.harness.plugins import build_harness_plugins
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
from veadk.extensions.harness.schemas import HarnessBaseModel
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


class HarnessExtension:
    """Small VeADK-facing wrapper for Harness plugin assembly.

    The extension owns no core Harness logic. It keeps the public VeADK entry
    point compact while delegating atomic behavior to the modules in this
    package.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        components: Iterable[str] | str | None = None,
        profile: str = "default",
        store: HarnessStoreProtocol | None = None,
        context_config: HarnessInvocationContextConfig | None = None,
        compaction_config: ToolResultCompactorConfig | None = None,
        verifier_config: FinalResponseVerifierConfig | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        if components is None:
            component_list = HarnessExtensionConfig().components
        elif isinstance(components, str):
            component_list = [
                item.strip() for item in components.split(",") if item.strip()
            ]
        else:
            component_list = [
                str(item).strip() for item in components if str(item).strip()
            ]
        self.config = HarnessExtensionConfig(
            enabled=enabled,
            components=component_list,
            profile=profile,
        )
        self.store = store
        self.context_config = context_config
        self.compaction_config = compaction_config
        self.verifier_config = verifier_config
        self.env = dict(env) if env is not None else None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> HarnessExtension:
        """Create an extension controlled by Harness environment variables."""

        values = dict(env or os.environ)
        return cls(enabled=harness_enabled_from_env(values), env=values)

    def plugins(self) -> list[BasePlugin]:
        """Build plugins for ``Runner(..., plugins=...)``."""

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


__all__ = ["HarnessExtension", "HarnessExtensionConfig"]
