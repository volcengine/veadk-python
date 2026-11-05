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
"""Automatic, still opt-in content-safety wiring for VeADK entry points.

``config.yaml`` with a ``tool.content_safety`` block is enough for agents run
through :class:`veadk.Runner` or deployed through AgentKit. When the block is
absent, ``provider`` is ``none``, or the caller already supplied a content
safety plugin, these helpers return without changing anything.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from google.adk.plugins import BasePlugin

from .config import (
    ContentSafetyConfig,
    ContentSafetyConfigError,
    load_content_safety_config_if_present,
)
from .factory import build_content_safety
from .types import Provider

_CONTENT_SAFETY_PLUGIN_NAMES = frozenset(
    {"content_safety_decision", "llm_shield_adapter"}
)


def _has_content_safety_plugin(plugins: Iterable[BasePlugin]) -> bool:
    return any(
        getattr(plugin, "name", None) in _CONTENT_SAFETY_PLUGIN_NAMES
        for plugin in plugins
    )


def _config_from_agent(agent: Any) -> ContentSafetyConfig | None:
    value = getattr(agent, "content_safety", None) if agent is not None else None

    if value is None:
        return load_content_safety_config_if_present()
    if value is False:
        return None
    if value is True:
        config = load_content_safety_config_if_present()
        if config is None:
            raise ContentSafetyConfigError(
                "content_safety=True requires a `tool.content_safety` block "
                "in config.yaml"
            )
        return config
    if isinstance(value, ContentSafetyConfig):
        return value
    if isinstance(value, Mapping):
        return ContentSafetyConfig.from_dict(dict(value))
    raise TypeError(
        "content_safety must be None, a bool, a mapping, or ContentSafetyConfig"
    )


def resolve_content_safety_plugin(
    agent: Any = None,
    *,
    existing: Iterable[BasePlugin] = (),
) -> BasePlugin | None:
    """Build the configured plugin, or ``None`` when content safety is off.

    ``agent.content_safety`` takes precedence over ``config.yaml``:

    - ``None`` (default): use ``config.yaml`` when it has a content-safety block
    - ``False``: explicitly disabled
    - ``True``: require ``config.yaml`` configuration
    - ``dict`` / :class:`ContentSafetyConfig`: use these values directly

    ``existing`` is inspected by plugin name so a caller that already mounted
    a content-safety plugin does not get a second one.
    """

    if _has_content_safety_plugin(existing):
        return None

    config = _config_from_agent(agent)
    if config is None or config.provider is Provider.NONE:
        return None

    return build_content_safety(
        config,
        ark_api_base=getattr(agent, "model_api_base", None),
        ark_api_key=getattr(agent, "model_api_key", None),
    )


def resolve_content_safety_plugins(
    agent: Any = None,
    existing: Iterable[BasePlugin] = (),
) -> list[BasePlugin]:
    """Return ``existing`` plus the configured content-safety plugin, if any."""

    plugins = list(existing)
    plugin = resolve_content_safety_plugin(agent, existing=plugins)
    if plugin is None:
        return plugins
    return [*plugins, plugin]
