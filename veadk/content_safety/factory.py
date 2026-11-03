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
from urllib.parse import urlsplit

from google.adk.plugins import BasePlugin

from veadk.decision import DecisionClient, DecisionJudge

from .config import ContentSafetyConfig, ContentSafetyConfigError
from .decider import ThresholdDecider
from .plugin import DecisionPlugin
from .state import StateBuilder
from .types import Provider


def _systemone_url(api_base: str) -> str:
    """Derive the Beta System One URL from an Ark API base.

    The design inherits the region/domain/gateway prefix and appends
    ``/api/v1/systemone``; it explicitly must not produce ``/api/v3/systemone``.
    """
    base = api_base.rstrip("/")
    for suffix in ("/api/v3", "/api/v1"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return f"{base}/api/v1/systemone"


def _ark_defaults(api_base: str | None, api_key: str | None) -> tuple[str, str]:
    if api_base and api_key:
        return api_base, api_key
    from veadk.config import settings

    return api_base or settings.model.api_base, api_key or settings.model.api_key


_ARK_HOST_SUFFIXES = (".volces.com", ".bytepluses.com")


def _is_ark_api_base(api_base: str) -> bool:
    """Return whether ``api_base`` is a known Ark HTTPS endpoint.

    The content-safety fallback must never derive a System One URL from an
    arbitrary model endpoint: doing so could send audited content to a
    non-Ark provider. Custom gateways must be configured explicitly through
    ``decision.api_url``.
    """
    try:
        parsed = urlsplit(api_base)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return (
        parsed.scheme == "https"
        and host.startswith("ark.")
        and host.endswith(_ARK_HOST_SUFFIXES)
    )


def _require_ark_api_base(api_base: str) -> None:
    if not _is_ark_api_base(api_base):
        raise ContentSafetyConfigError(
            "Cannot derive the System One endpoint from a non-Ark model API base. "
            "Set decision.api_url explicitly to use a custom endpoint."
        )


def _resolve_decision_connection(
    config: ContentSafetyConfig,
    ark_api_base: str | None,
    ark_api_key: str | None,
) -> tuple[str, str]:
    """Resolve the System One URL and key without an unsafe cross-provider mix."""
    api_url = config.decision.api_url
    api_key = config.decision.api_key

    if api_url:
        if api_key:
            return api_url, api_key
        if not _is_ark_api_base(api_url):
            raise ContentSafetyConfigError(
                "decision.api_key is required when decision.api_url is not an Ark "
                "endpoint; refusing to reuse the Ark credential for a custom endpoint."
            )
        _, fallback_key = _ark_defaults(ark_api_base, ark_api_key)
        return api_url, fallback_key

    base, fallback_key = _ark_defaults(ark_api_base, ark_api_key)
    _require_ark_api_base(base)
    return _systemone_url(base), api_key or fallback_key


def build_content_safety(
    config: ContentSafetyConfig,
    *,
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
            api_url, api_key = _resolve_decision_connection(
                config, ark_api_base, ark_api_key
            )
            judge = DecisionClient(
                endpoint=api_url,
                api_key=api_key,
                model=config.decision.model,
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
