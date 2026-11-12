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
"""Explicit factory; nothing here runs unless a caller invokes it."""

from __future__ import annotations

from typing import Any

from google.adk.plugins import BasePlugin

from veadk.decision import (
    DecisionClient,
    DecisionJudge,
    DecisionConfig,
    load_decision_config,
    resolve_decision_connection,
)

from .config import ContentSafetyConfig
from .decider import ThresholdDecider
from .plugin import DecisionPlugin
from .state import StateBuilder
from .types import Provider


def build_content_safety(
    config: ContentSafetyConfig,
    *,
    decision: DecisionConfig | None = None,
    client: DecisionJudge | None = None,
    decider: ThresholdDecider | None = None,
    state_builder: StateBuilder | None = None,
    llm_shield_inner: Any | None = None,
    ark_api_base: str | None = None,
    ark_api_key: str | None = None,
) -> BasePlugin | None:
    """Build the configured plugin, or ``None`` when disabled.

    ``provider="none"`` is the default. Providers are selected explicitly and
    never fall back to one another.

    ``ark_api_base`` / ``ark_api_key`` let a caller pass the current Agent's
    effective Ark connection when it differs from the global configuration.
    When no explicit ``decision.api_url`` is configured, the fallback base must
    be a known Ark endpoint; arbitrary model providers are rejected rather than
    receiving audited content.
    """

    if config.provider is Provider.NONE:
        return None

    if config.provider is Provider.DECISION:
        judge = client
        if judge is None:
            connection = decision if decision is not None else load_decision_config()
            api_url, api_key = resolve_decision_connection(
                connection, ark_api_base, ark_api_key
            )
            judge = DecisionClient(
                endpoint=api_url,
                api_key=api_key,
                model=connection.model,
            )
        return DecisionPlugin(
            config=config,
            client=judge,
            decider=decider,
            state_builder=state_builder,
        )

    if config.provider is Provider.LLM_SHIELD:
        from .adapters.llm_shield import LLMShieldPluginAdapter

        return LLMShieldPluginAdapter.from_config(config, inner=llm_shield_inner)

    raise ValueError(f"unsupported content-safety provider: {config.provider}")
