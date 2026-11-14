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
from veadk.decision import (
    DecisionClient,
    DecisionConfig,
    load_decision_config,
    resolve_decision_connection,
)
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
    decision: DecisionConfig | None = None,
    store: RouteStore | None = None,
    judge: Any | None = None,
) -> tuple[RoutingLlm, Any]:
    """Build the model pool and final request binder.

    ``judge`` is injectable for tests; production uses a ``DecisionClient``
    whose Ark endpoint is derived from the Agent's effective model connection.
    """

    strong_model = _strong_model(config, agent)
    _validate_model_contract(strong_model)
    runtimes = [
        SimpleModelRuntime(config=model, llm=_build_model(agent, model))
        for model in config.simple_models
    ]
    registry = ModelRegistry(runtimes=runtimes)
    route_store = store or get_route_store()

    if judge is None:
        connection = decision if decision is not None else load_decision_config()
        endpoint, api_key = resolve_decision_connection(
            connection,
            getattr(agent, "model_api_base", None),
            getattr(agent, "model_api_key", None),
        )
        judge = DecisionClient(
            endpoint=endpoint,
            api_key=api_key,
            model=connection.model,
            timeout=config.decision_timeout,
        )

    classifier = QueryClassifier(config, judge, registry)
    router = RoutingLlm(
        model=getattr(strong_model, "model", config.strong_model or ""),
        strong_model=strong_model,
        runtimes=runtimes,
        registry=registry,
        store=route_store,
        classifier=classifier,
        config=config,
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


def _validate_model_contract(model: BaseLlm) -> None:
    from veadk.configs.routing_configs import _REQUEST_OVERRIDE_FIELDS

    extra = getattr(model, "_additional_args", {}) or {}
    body = extra.get("extra_body") or {}
    if _REQUEST_OVERRIDE_FIELDS.intersection(extra) or (
        _REQUEST_OVERRIDE_FIELDS | {"model"}
    ).intersection(body):
        raise QueryRoutingConfigError(
            "model transport options must not override routed requests"
        )
    if getattr(model, "fallbacks", None) or extra.get("fallbacks"):
        raise QueryRoutingConfigError(
            "query routing fixes the model for the entire turn; remove model_fallbacks"
        )


def _build_model(agent: Any, specification: Any) -> BaseLlm:
    from veadk.configs.routing_configs import SimpleModelConfig
    from veadk.models.ark_llm import ArkLlm
    from veadk.models.retrying_lite_llm import RetryingLiteLlm

    spec = (
        SimpleModelConfig(name=specification)
        if isinstance(specification, str)
        else specification
    )
    provider = spec.provider or getattr(agent, "model_provider", "openai")
    full_name = spec.name if "/" in spec.name else f"{provider}/{spec.name}"
    api_base = spec.api_base or getattr(agent, "model_api_base", "")
    explicit_key = spec.api_key_value
    if (
        spec.api_base
        and spec.api_base.rstrip("/")
        != getattr(agent, "model_api_base", "").rstrip("/")
        and not explicit_key
    ):
        raise QueryRoutingConfigError(
            "an independent api_base requires api_key or api_key_env"
        )
    api_key = explicit_key or getattr(agent, "model_api_key", "")
    # Endpoint-specific defaults must not cross provider boundaries.
    extra = (
        dict(getattr(agent, "model_extra_config", {}) or {})
        if not spec.api_base
        else {}
    )
    extra.update(spec.extra_config)
    responses = (
        spec.api == "responses"
        if spec.api
        else getattr(agent, "enable_responses", False)
    )
    kwargs = dict(
        model=full_name, api_key=api_key, api_base=api_base, fallbacks=None, **extra
    )
    if responses:
        model = ArkLlm(
            enable_responses_cache=getattr(agent, "enable_responses_cache", True),
            **kwargs,
        )
    else:
        model = RetryingLiteLlm(**kwargs)
    _validate_model_contract(model)
    return model
