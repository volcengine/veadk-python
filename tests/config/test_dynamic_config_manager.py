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

from unittest.mock import AsyncMock, MagicMock

import pytest

import veadk.configs.dynamic_config_manager as dynamic_config_manager_module
from veadk.configs.dynamic_config_manager import DynamicConfigManager


@pytest.mark.asyncio
async def test_create_config_uses_custom_group_for_listener(monkeypatch):
    monkeypatch.setenv("NACOS_ENDPOINT", "localhost")
    monkeypatch.setenv("NACOS_PORT", "8848")
    monkeypatch.setenv("NACOS_USERNAME", "nacos")
    monkeypatch.setenv("NACOS_PASSWORD", "password")

    client_config = MagicMock()
    monkeypatch.setattr(
        dynamic_config_manager_module,
        "ClientConfig",
        MagicMock(return_value=client_config),
    )

    config_client = MagicMock()
    config_client.publish_config = AsyncMock(return_value=True)
    config_client.add_listener = AsyncMock()
    create_config_service = AsyncMock(return_value=config_client)
    monkeypatch.setattr(
        dynamic_config_manager_module.NacosConfigService,
        "create_config_service",
        create_config_service,
    )

    manager = DynamicConfigManager(MagicMock())
    custom_group = "CUSTOM_GROUP"

    returned_client = await manager.create_config(
        configs={"agent": []},
        instance_name="test-instance",
        group_id=custom_group,
    )

    published_param = config_client.publish_config.await_args.kwargs["param"]
    listener_group = config_client.add_listener.await_args.kwargs["group"]

    assert returned_client is config_client
    assert published_param.group == custom_group
    assert listener_group == custom_group
