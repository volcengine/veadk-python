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

from collections.abc import AsyncGenerator
from types import SimpleNamespace

import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from veadk.decision import (
    DecisionConfig,
    DecisionConfigError,
    resolve_decision_connection,
)
from veadk.configs.routing_configs import (
    QueryRoutingConfig,
    QueryRoutingConfigError,
)
from veadk.models.ark_llm import ArkLlm
from veadk.models.retrying_lite_llm import RetryingLiteLlm
from veadk.routing import factory
from veadk.routing.llm import RoutingLlm

ARK_BASE = "https://ark.cn-beijing.volces.com/api/v3"
SYSTEMONE = "https://ark.cn-beijing.volces.com/api/v1/systemone"


class FakeStrongLlm(BaseLlm):
    model: str = "strong"

    async def generate_content_async(
        self, llm_request, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text="strong")])
        )


class FakeJudge:
    async def judge(self, *, state, questions):
        return SimpleNamespace(answers={})


def fake_agent(**overrides):
    values = {
        "model_name": "strong",
        "model": FakeStrongLlm(),
        "model_provider": "ark",
        "model_api_base": ARK_BASE,
        "model_api_key": "agent-key",
        "model_extra_config": {},
        "enable_responses": False,
        "enable_responses_cache": True,
        "runtime": "adk",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def config(**overrides):
    values = {"simple_models": ["cheap"]}
    values.update(overrides)
    return QueryRoutingConfig.model_validate(values)


def test_false_disables_routing(monkeypatch):
    def unexpected():
        raise AssertionError("must not load configuration")

    monkeypatch.setattr(factory, "load_query_routing_config_if_present", unexpected)
    monkeypatch.setattr(factory, "load_query_routing_config", unexpected)
    assert factory.resolve_query_routing_config(False) is None


def test_none_auto_detects(monkeypatch):
    sentinel = config()
    monkeypatch.setattr(
        factory, "load_query_routing_config_if_present", lambda: sentinel
    )
    assert factory.resolve_query_routing_config(None) is sentinel


def test_true_requires_configuration(monkeypatch):
    sentinel = config()
    monkeypatch.setattr(factory, "load_query_routing_config", lambda: sentinel)
    assert factory.resolve_query_routing_config(True) is sentinel


def test_config_instance_is_returned_unchanged():
    value = config()
    assert factory.resolve_query_routing_config(value) is value


def test_mapping_is_validated():
    value = factory.resolve_query_routing_config(
        {"simple_models": ["cheap"], "strong_model": "strong"}
    )
    assert value.simple_models[0].name == "cheap"
    assert value.strong_model == "strong"


def test_invalid_value_is_rejected():
    with pytest.raises(QueryRoutingConfigError, match="must be None"):
        factory.resolve_query_routing_config("config.yaml")


def test_responses_cache_is_supported():
    agent = fake_agent(enable_responses=True, enable_responses_cache=True)
    router, _ = factory.build_query_routing(config(), agent, judge=FakeJudge())
    assert router.runtimes[0].llm.enable_responses_cache is True


def test_build_uses_the_agent_model_as_strong_tier():
    agent = fake_agent()
    router, callback = factory.build_query_routing(config(), agent, judge=FakeJudge())
    assert isinstance(router, RoutingLlm)
    assert router.strong_model is agent.model
    assert router.model == "strong"
    assert [runtime.config.name for runtime in router.runtimes] == ["cheap"]
    assert callable(callback)


def test_build_constructs_a_decision_client_from_ark_connection(monkeypatch):
    captured = {}

    class Recorder:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(factory, "DecisionClient", Recorder)
    factory.build_query_routing(config(), fake_agent())

    assert captured == {
        "endpoint": SYSTEMONE,
        "api_key": "agent-key",
        "model": "doubao-seed-2-1-lite-260915",
        "timeout": 2.0,
    }


def test_build_uses_explicit_strong_model(monkeypatch):
    built = FakeStrongLlm(model="explicit")
    monkeypatch.setattr(factory, "_build_model", lambda agent, name: built)

    router, _ = factory.build_query_routing(
        config(strong_model="stronger"), fake_agent(), judge=FakeJudge()
    )
    assert router.strong_model is built


def test_strong_model_defaults_to_agent_model():
    agent = fake_agent()
    assert factory._strong_model(config(), agent) is agent.model


def test_strong_model_matching_primary_name_reuses_agent_model():
    agent = fake_agent(model_name="strong")
    assert factory._strong_model(config(strong_model="strong"), agent) is agent.model


def test_strong_model_differs_from_primary(monkeypatch):
    built = FakeStrongLlm(model="built")
    calls = []

    def build(agent, name):
        calls.append((agent, name))
        return built

    monkeypatch.setattr(factory, "_build_model", build)
    agent = fake_agent()
    assert factory._strong_model(config(strong_model="stronger"), agent) is built
    assert calls == [(agent, "stronger")]


def test_primary_model_name_accepts_a_list():
    assert factory._primary_model_name(fake_agent(model_name=["a", "b"])) == "a"
    assert factory._primary_model_name(fake_agent(model_name=[])) is None
    assert factory._primary_model_name(fake_agent(model_name="a")) == "a"


def test_build_model_prefixes_provider_for_plain_names():
    model = factory._build_model(fake_agent(), "cheap")
    assert isinstance(model, RetryingLiteLlm)
    assert model.model == "ark/cheap"


def test_build_model_keeps_qualified_names():
    model = factory._build_model(fake_agent(), "openai/cheap")
    assert model.model == "openai/cheap"


def test_build_model_uses_ark_responses_without_cache():
    model = factory._build_model(fake_agent(enable_responses=True), "cheap")
    assert isinstance(model, ArkLlm)
    assert model.model == "ark/cheap"
    assert model.enable_responses_cache is True


def resolve_for_agent(config, agent):
    return resolve_decision_connection(
        config, agent.model_api_base, agent.model_api_key
    )


def test_decision_connection_uses_explicit_url_and_key():
    agent = fake_agent(model_api_base="https://api.openai.com/v1", model_api_key="x")
    decision = DecisionConfig(
        **{
            "api_url": "https://ark.cn-beijing.volces.com/api/v1/systemone",
            "api_key": "explicit",
        }
    )
    assert resolve_for_agent(decision, agent) == (
        "https://ark.cn-beijing.volces.com/api/v1/systemone",
        "explicit",
    )


def test_decision_connection_refuses_cross_provider_endpoint():
    decision = DecisionConfig(**{"api_url": "https://example.com/systemone"})
    with pytest.raises(DecisionConfigError, match="not an Ark endpoint"):
        resolve_for_agent(decision, fake_agent())


def test_decision_connection_requires_ark_model_base_for_ark_url():
    decision = DecisionConfig(**{"api_url": SYSTEMONE})
    agent = fake_agent(model_api_base="https://api.openai.com/v1")
    with pytest.raises(DecisionConfigError, match="fallback Ark API base"):
        resolve_for_agent(decision, agent)


def test_decision_connection_requires_a_key_for_ark_url():
    decision = DecisionConfig(**{"api_url": SYSTEMONE})
    agent = fake_agent(model_api_key="")
    with pytest.raises(DecisionConfigError, match="API key is not configured"):
        resolve_for_agent(decision, agent)


def test_decision_connection_reuses_ark_key_for_ark_url():
    decision = DecisionConfig(**{"api_url": SYSTEMONE})
    assert resolve_for_agent(decision, fake_agent()) == (
        SYSTEMONE,
        "agent-key",
    )


def test_decision_connection_rejects_non_ark_model_base_without_url():
    agent = fake_agent(model_api_base="https://api.openai.com/v1")
    with pytest.raises(DecisionConfigError, match="cannot derive"):
        resolve_for_agent(DecisionConfig(), agent)


def test_decision_connection_derives_systemone_from_ark_base():
    assert resolve_for_agent(DecisionConfig(), fake_agent()) == (
        SYSTEMONE,
        "agent-key",
    )


def test_decision_connection_prefers_explicit_key_when_deriving():
    decision = DecisionConfig(**{"api_key": "explicit"})
    assert resolve_for_agent(decision, fake_agent()) == (
        SYSTEMONE,
        "explicit",
    )


def test_decision_connection_requires_a_key_when_deriving():
    agent = fake_agent(model_api_key="")
    with pytest.raises(DecisionConfigError, match="API key is not configured"):
        resolve_for_agent(DecisionConfig(), agent)


def test_routing_rejects_underlying_model_fallbacks():
    model = ArkLlm(model="openai/strong", fallbacks=["openai/other"])
    with pytest.raises(QueryRoutingConfigError, match="entire turn"):
        factory.build_query_routing(
            config(), fake_agent(model=model), judge=FakeJudge()
        )


def test_independent_endpoint_never_inherits_credentials_or_provider_extras():
    from veadk.configs.routing_configs import SimpleModelConfig

    spec = SimpleModelConfig(name="cheap", api_base="https://other.example/v1")
    with pytest.raises(QueryRoutingConfigError, match="independent api_base"):
        factory._build_model(fake_agent(), spec)
    spec = SimpleModelConfig(
        name="cheap",
        api_base="https://other.example/v1",
        api_key="other-only",
        api="chat_completions",
    )
    model = factory._build_model(
        fake_agent(model_extra_config={"extra_headers": {"provider-only": "yes"}}), spec
    )
    assert model._additional_args["api_key"] == "other-only"
    assert "provider-only" not in str(model._additional_args)


@pytest.mark.parametrize(
    "extra",
    [
        {"previous_response_id": "stale-id"},
        {"extra_body": {"model": "other-model"}},
    ],
)
def test_parent_transport_options_cannot_bypass_fixed_routing(extra):
    model = ArkLlm(model="openai/strong", **extra)
    with pytest.raises(QueryRoutingConfigError, match="override"):
        factory.build_query_routing(
            config(), fake_agent(model=model), judge=FakeJudge()
        )
