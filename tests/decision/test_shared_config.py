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
"""Common connection configuration stays independent of consumer policy."""

import os

import pytest
import yaml
from pydantic import ValidationError

from veadk.configs.routing_configs import (
    QueryRoutingConfig,
    load_query_routing_config_if_present,
)
from veadk.content_safety import (
    ContentSafetyConfig,
    load_content_safety_config_if_present,
)
from veadk.decision import DecisionConfig, DecisionConfigError, load_decision_config


def config_file(tmp_path, **overrides):
    document = {
        "decision": {
            "model": "shared-judge",
            "api_url": "https://shared.example/systemone",
            "api_key": "test-placeholder",
        },
        **overrides,
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(document))
    return path


def test_only_common_import_is_public():
    import veadk.content_safety as safety
    import veadk.content_safety.config as config

    assert not hasattr(safety, "DecisionConfig")
    assert not hasattr(config, "DecisionConfig")


@pytest.mark.parametrize(
    "consumer,kwargs",
    [
        (QueryRoutingConfig, {"simple_models": ["candidate"]}),
        (ContentSafetyConfig, {"provider": "decision"}),
    ],
)
def test_old_nested_connection_is_rejected(consumer, kwargs):
    with pytest.raises(ValidationError, match="decision"):
        consumer(**kwargs, decision={"model": "old"})


def test_root_connection_is_immutable_and_enables_nothing(tmp_path):
    path = config_file(tmp_path)
    first = load_decision_config(path)
    second = load_decision_config(path)
    assert first.model == second.model == "shared-judge"
    assert first is not second
    with pytest.raises(ValidationError):
        first.model = "changed"
    assert load_query_routing_config_if_present(path) is None
    assert load_content_safety_config_if_present(path) is None


def test_explicit_code_ignores_file_and_environment(tmp_path, monkeypatch):
    config_file(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DECISION_MODEL", "env")
    assert DecisionConfig(model="code").model == "code"


def test_common_environment_overrides_file(tmp_path, monkeypatch):
    path = config_file(tmp_path)
    monkeypatch.setenv("DECISION_MODEL", "environment-judge")
    monkeypatch.setenv("TOOL_CONTENT_SAFETY_DECISION_MODEL", "old-ignored")
    assert load_decision_config(path).model == "environment-judge"


@pytest.mark.parametrize("value", [[], "invalid", {"unsupported": True}])
def test_invalid_root_config_fails(tmp_path, value):
    with pytest.raises(DecisionConfigError, match="decision"):
        load_decision_config(config_file(tmp_path, decision=value))


def test_environment_endpoint_cannot_inherit_file_key(tmp_path, monkeypatch):
    path = config_file(tmp_path)
    monkeypatch.setenv("DECISION_API_URL", "https://other.example/systemone")
    with pytest.raises(DecisionConfigError, match="DECISION_API_KEY"):
        load_decision_config(path)
    monkeypatch.setenv("DECISION_API_KEY", "other-placeholder")
    assert load_decision_config(path).api_key_value == "other-placeholder"


def test_structured_config_does_not_become_process_environment(tmp_path, monkeypatch):
    from veadk.utils.misc import set_envs

    path = config_file(
        tmp_path,
        query_routing={"simple_models": ["candidate"]},
        tool={"content_safety": {"provider": "decision"}},
    )
    monkeypatch.setattr(os, "environ", os.environ.copy())
    before = dict(os.environ)
    document, exported = set_envs(str(path))
    assert document["decision"]["model"] == "shared-judge"
    assert not exported
    assert dict(os.environ) == before


def test_agent_shares_values_but_never_client_instances(tmp_path, monkeypatch):
    from veadk import Agent
    from veadk.content_safety import resolve_content_safety_plugin

    config_file(tmp_path)
    monkeypatch.chdir(tmp_path)
    shared = DecisionConfig(
        api_url="https://inline.example/systemone",
        api_key="inline-placeholder",
        model="inline-judge",
    )
    agent = Agent(
        name="shared",
        model_name="strong",
        model_api_key="model-placeholder",
        decision=shared,
        query_routing={"simple_models": ["candidate"], "decision_timeout": 3},
        content_safety={"provider": "decision"},
    )
    safety = resolve_content_safety_plugin(agent)
    routing = agent.model.classifier._judge
    assert routing is not safety._client
    assert routing._model == safety._client._model == "inline-judge"
    assert (
        routing.endpoint
        == safety._client.endpoint
        == "https://inline.example/systemone"
    )
    assert agent.decision == shared
    assert routing._timeout != safety._client._timeout


@pytest.mark.parametrize(
    "text",
    [
        "[]",
        "decision: []",
        "decision: {model: a, model: b}",
        "decision: [",
        "decision: {1: bad}",
    ],
)
def test_malformed_common_yaml_fails(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text)
    with pytest.raises(DecisionConfigError):
        load_decision_config(path)


def test_missing_explicit_file_fails_but_missing_discovered_file_defaults(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    assert load_decision_config() == DecisionConfig()
    with pytest.raises(DecisionConfigError):
        load_decision_config(tmp_path / "absent.yaml")


def test_root_absent_environment_can_supply_connection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DECISION_API_KEY", "environment-placeholder")
    assert load_decision_config().api_key_value == "environment-placeholder"


def test_explicit_decision_key_does_not_resolve_unused_global_credentials(monkeypatch):
    import veadk.config as config
    from types import SimpleNamespace
    from veadk.decision import resolve_decision_connection

    class Model:
        api_base = "https://ark.cn-beijing.volces.com/api/v3"

        @property
        def api_key(self):
            raise AssertionError(
                "unused global key resolution may call a cloud service"
            )

    monkeypatch.setattr(config, "settings", SimpleNamespace(model=Model()))
    assert resolve_decision_connection(
        DecisionConfig(api_key="explicit-placeholder")
    ) == ("https://ark.cn-beijing.volces.com/api/v1/systemone", "explicit-placeholder")
    with pytest.raises(DecisionConfigError, match="not an Ark"):
        resolve_decision_connection(DecisionConfig(), "https://unrelated.example/v1")


@pytest.mark.parametrize(
    "consumer,kwargs",
    [
        (QueryRoutingConfig, {"simple_models": ["candidate"]}),
        (ContentSafetyConfig, {"provider": "decision"}),
    ],
)
def test_rejecting_removed_connection_never_prints_its_key(consumer, kwargs):
    with pytest.raises(ValidationError) as error:
        consumer(**kwargs, decision={"api_key": "obsolete-key-placeholder"})
    assert "obsolete-key-placeholder" not in str(error.value)
