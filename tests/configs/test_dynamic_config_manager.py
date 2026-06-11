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

"""Unit tests for ``veadk.configs.dynamic_config_manager``.

The module imports the ``v2.nacos`` SDK at module top level, which is not
installed in the test environment, so we register lightweight stubs in
``sys.modules`` before importing. All Nacos / MSE credential access is mocked;
no network calls are performed.
"""

import json
import sys
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ``v2.nacos`` is an optional runtime dependency that is not installed in the
# test environment. Register stubs so the module under test can be imported.
for _name in (
    "v2",
    "v2.nacos",
    "v2.nacos.config",
    "v2.nacos.config.model",
    "v2.nacos.config.model.config_param",
):
    sys.modules.setdefault(_name, MagicMock())

from veadk.configs import dynamic_config_manager as dcm  # noqa: E402
from veadk.consts import (  # noqa: E402
    DEFAULT_NACOS_GROUP,
    DEFAULT_NACOS_INSTANCE_NAME,
)


def _make_agent(agent_id: str = "agent-1") -> MagicMock:
    agent = MagicMock()
    agent.id = agent_id
    agent.name = "name"
    agent.description = "description"
    agent.model_name = "model"
    agent.instruction = "instruction"
    return agent


def test_init_wraps_single_agent_in_list():
    agent = _make_agent()
    manager = dcm.DynamicConfigManager(agent)
    assert manager.agents == [agent]


def test_init_keeps_list_of_agents():
    agents = [_make_agent("a"), _make_agent("b")]
    manager = dcm.DynamicConfigManager(cast("list[dcm.Agent]", agents))
    assert manager.agents == agents


def test_register_agent_single_and_list():
    manager = dcm.DynamicConfigManager(_make_agent("a"))
    manager.register_agent(_make_agent("b"))
    assert len(manager.agents) == 2

    manager.register_agent([_make_agent("c"), _make_agent("d")])
    assert len(manager.agents) == 4


def test_update_agent_applies_matching_config():
    agent = _make_agent("agent-1")
    agent.model_name = "old-model"
    manager = dcm.DynamicConfigManager(agent)

    configs = {
        "agent": [
            {
                "id": "agent-1",
                "name": "new-name",
                "description": "new-description",
                "model_name": "new-model",
                "instruction": "new-instruction",
            }
        ]
    }
    manager.update_agent(configs)

    assert agent.name == "new-name"
    assert agent.description == "new-description"
    assert agent.instruction == "new-instruction"
    # model_name changed -> update_model must be invoked with the new value.
    agent.update_model.assert_called_once_with(model_name="new-model")


def test_update_agent_skips_when_model_unchanged():
    agent = _make_agent("agent-1")
    agent.model_name = "same-model"
    manager = dcm.DynamicConfigManager(agent)

    configs = {
        "agent": [
            {
                "id": "agent-1",
                "name": "n",
                "description": "d",
                "model_name": "same-model",
                "instruction": "i",
            }
        ]
    }
    manager.update_agent(configs)

    agent.update_model.assert_not_called()


def test_update_agent_ignores_non_matching_id():
    agent = _make_agent("agent-1")
    manager = dcm.DynamicConfigManager(agent)

    original_name = agent.name
    manager.update_agent(
        {
            "agent": [
                {
                    "id": "different-id",
                    "name": "should-not-apply",
                    "description": "d",
                    "model_name": "m",
                    "instruction": "i",
                }
            ]
        }
    )
    assert agent.name == original_name
    agent.update_model.assert_not_called()


@pytest.mark.asyncio
async def test_handle_config_update_parses_json_and_updates(monkeypatch):
    manager = dcm.DynamicConfigManager(_make_agent("agent-1"))

    captured = {}

    def fake_update_agent(content):
        captured["content"] = content

    monkeypatch.setattr(manager, "update_agent", fake_update_agent)

    payload = {"agent": [{"id": "agent-1"}]}
    await manager.handle_config_update(
        tenant="t", data_id="veadk", group="g", content=json.dumps(payload)
    )

    assert captured["content"] == payload


@pytest.mark.asyncio
async def test_create_config_uses_defaults_and_publishes(monkeypatch):
    """create_config falls back to default instance/group, builds the default
    agent config payload, publishes it, and registers a listener."""
    agent = _make_agent("agent-1")
    manager = dcm.DynamicConfigManager(agent)

    monkeypatch.setenv("NACOS_ENDPOINT", "127.0.0.1")
    monkeypatch.setenv("NACOS_PORT", "8848")
    monkeypatch.setenv("NACOS_USERNAME", "nacos")
    monkeypatch.setenv("NACOS_PASSWORD", "secret")

    config_client = MagicMock()
    config_client.publish_config = AsyncMock(return_value=True)
    config_client.add_listener = AsyncMock()

    create_service = AsyncMock(return_value=config_client)

    with (
        patch.object(dcm.NacosConfigService, "create_config_service", create_service),
        patch.object(dcm, "ConfigParam") as mock_param,
    ):
        result = await manager.create_config()

    assert result is config_client

    # publish_config called once; the JSON content carries the default agent
    # payload assembled from the registered agents.
    config_client.publish_config.assert_awaited_once()
    _, kwargs = mock_param.call_args
    published = json.loads(kwargs["content"])
    assert published["agent"][0]["id"] == "agent-1"
    assert kwargs["data_id"] == "veadk"
    assert kwargs["group"] == DEFAULT_NACOS_GROUP

    config_client.add_listener.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_config_asserts_on_publish_failure(monkeypatch):
    manager = dcm.DynamicConfigManager(_make_agent("agent-1"))

    monkeypatch.setenv("NACOS_ENDPOINT", "127.0.0.1")
    monkeypatch.setenv("NACOS_PORT", "8848")
    monkeypatch.setenv("NACOS_USERNAME", "nacos")
    monkeypatch.setenv("NACOS_PASSWORD", "secret")

    config_client = MagicMock()
    config_client.publish_config = AsyncMock(return_value=False)
    config_client.add_listener = AsyncMock()

    with (
        patch.object(
            dcm.NacosConfigService,
            "create_config_service",
            AsyncMock(return_value=config_client),
        ),
        patch.object(dcm, "ConfigParam"),
        pytest.raises(AssertionError, match="publish config to nacos failed"),
    ):
        await manager.create_config(
            instance_name=DEFAULT_NACOS_INSTANCE_NAME,
            group_id=DEFAULT_NACOS_GROUP,
        )


@pytest.mark.asyncio
async def test_create_config_falls_back_to_mse_credentials(monkeypatch):
    """When Nacos env vars are absent, MSE credentials are fetched instead."""
    manager = dcm.DynamicConfigManager(_make_agent("agent-1"))

    for var in ("NACOS_ENDPOINT", "NACOS_PORT", "NACOS_USERNAME", "NACOS_PASSWORD"):
        monkeypatch.delenv(var, raising=False)

    credentials = MagicMock(
        endpoint="mse-endpoint",
        port="8848",
        username="mse-user",
        password="mse-pass",
    )

    config_client = MagicMock()
    config_client.publish_config = AsyncMock(return_value=True)
    config_client.add_listener = AsyncMock()

    with (
        patch.object(dcm, "get_mse_cridential", return_value=credentials) as mock_cred,
        patch.object(
            dcm.NacosConfigService,
            "create_config_service",
            AsyncMock(return_value=config_client),
        ),
        patch.object(dcm, "ConfigParam"),
    ):
        await manager.create_config(instance_name="my-instance")

    mock_cred.assert_called_once_with(instance_name="my-instance")
