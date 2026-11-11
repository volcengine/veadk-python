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
"""Build routing components from configuration and Agent model settings."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from google.adk.models.base_llm import BaseLlm

from veadk.configs.routing_configs import (
    QueryRoutingConfig,
    QueryRoutingConfigError,
    load_query_routing_config,
    load_query_routing_config_if_present,
)
from veadk.content_safety.factory import _is_ark_api_base, _systemone_url
from veadk.decision import DecisionClient
from veadk.routing.callback import build_before_model_callback
from veadk.routing.classifier import QueryClassifier
from veadk.routing.llm import RoutingLlm
from veadk.routing.registry import ModelRegistry, SimpleModelRuntime
from veadk.routing.store import RouteStore, get_route_store


def resolve_query_routing_config(
    value: Any,
) -> QueryRoutingConfig | None:
    """Resolve the Agent's ``query_routing`` value.

    ``None`` auto-detects a ``query_routing`` block in ``config.yaml``;
    ``False`` disables routing explicitly; ``True`` requires the YAML block.
    A mapping or a :class:`QueryRoutingConfig` supplies configuration directly.
    """

    if value is False:
        return None
    if value is None:
        return load_query_routing_config_if_present()
    if value is True:
        return load_query_routing_config()
    if isinstance(value, QueryRoutingConfig):
        return value
    if isinstance(value, Mapping):
        return QueryRoutingConfig.model_validate(dict(value))
    raise QueryRoutingConfigError(
        "query_routing must be None, True, False, a mapping, or QueryRoutingConfig"
    )


def build_query_routing(
    config: QueryRoutingConfig,
    agent: Any,
    *,
    store: RouteStore | None = None,
    judge: Any | None = None,
) -> tuple[RoutingLlm, Any]:
    """Build the routing proxy and its ``before_model_callback``.

    ``judge`` is injectable for tests; production uses a ``DecisionClient``
    whose Ark endpoint is derived from the Agent's effective model connection.
    """

    if getattr(agent, "enable_responses", False) and getattr(
        agent, "enable_responses_cache", True
    ):
        raise QueryRoutingConfigError(
            "query routing is incompatible with Responses cache continuation; "
            "set enable_responses_cache=False or disable query_routing"
        )

    strong_model = _strong_model(config, agent)
    runtimes = [
        SimpleModelRuntime(config=model, llm=_build_model(agent, model.name))
        for model in config.simple_models
    ]
    registry = ModelRegistry(runtimes=runtimes)
    route_store = store or get_route_store()

    if judge is None:
        endpoint, api_key = _resolve_decision_connection(config, agent)
        judge = DecisionClient(
            endpoint=endpoint,
            api_key=api_key,
            model=config.decision.model,
            timeout=config.decision_timeout,
        )

    classifier = QueryClassifier(config, judge, registry)
    router = RoutingLlm(
        model=getattr(strong_model, "model", config.strong_model or ""),
        strong_model=strong_model,
        runtimes=runtimes,
        registry=registry,
        store=route_store,
    )
    callback = build_before_model_callback(classifier, route_store, config)
    return router, callback


def _strong_model(config: QueryRoutingConfig, agent: Any) -> BaseLlm:
    strong_name = config.strong_model
    primary = _primary_model_name(agent)
    if strong_name is None or strong_name == primary:
        return agent.model
    return _build_model(agent, strong_name)


def _primary_model_name(agent: Any) -> str | None:
    model_name = getattr(agent, "model_name", None)
    if isinstance(model_name, list):
        return model_name[0] if model_name else None
    return model_name


def _build_model(agent: Any, model_name: str) -> BaseLlm:
    provider = getattr(agent, "model_provider", "") or ""
    full_name = model_name if "/" in model_name else f"{provider}/{model_name}"
    extra = dict(getattr(agent, "model_extra_config", {}) or {})

    if getattr(agent, "enable_responses", False):
        from veadk.models.ark_llm import ArkLlm

        return ArkLlm(
            model=full_name,
            api_key=getattr(agent, "model_api_key", ""),
            api_base=getattr(agent, "model_api_base", ""),
            fallbacks=None,
            enable_responses_cache=False,
            **extra,
        )

    from veadk.models.retrying_lite_llm import RetryingLiteLlm

    return RetryingLiteLlm(
        model=full_name,
        api_key=getattr(agent, "model_api_key", ""),
        api_base=getattr(agent, "model_api_base", ""),
        fallbacks=None,
        **extra,
    )


def _resolve_decision_connection(
    config: QueryRoutingConfig, agent: Any
) -> tuple[str, str]:
    """Resolve the System One URL and key without crossing providers.

    Mirrors the content-safety rule: an Ark credential is never sent to a
    non-Ark endpoint, and a non-Ark credential is never sent to Ark.
    """

    api_base = getattr(agent, "model_api_base", "") or ""
    api_key = getattr(agent, "model_api_key", "") or ""
    explicit_key = config.decision.api_key_value

    if config.decision.api_url:
        endpoint = config.decision.api_url
        if explicit_key:
            return endpoint, explicit_key
        if not _is_ark_api_base(endpoint):
            raise QueryRoutingConfigError(
                "decision.api_key is required when decision.api_url is not an Ark "
                "endpoint; refusing to reuse the Ark credential for a custom endpoint"
            )
        if not _is_ark_api_base(api_base):
            raise QueryRoutingConfigError(
                "decision.api_key is required when the fallback Ark API base is "
                "not an Ark endpoint"
            )
        if not api_key:
            raise QueryRoutingConfigError("decision API key is not configured")
        return endpoint, api_key

    if not _is_ark_api_base(api_base):
        raise QueryRoutingConfigError(
            "cannot derive the System One endpoint from a non-Ark model API base; "
            "set query_routing.decision.api_url explicitly"
        )
    key = explicit_key or api_key
    if not key:
        raise QueryRoutingConfigError("decision API key is not configured")
    return _systemone_url(api_base), key
