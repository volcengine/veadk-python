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

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from veadk.integrations.mpa.managed.gateway_cloud import APIGClientError, GatewayCloud


def test_new_gateway_matches_standard_shared_specification():
    cloud = GatewayCloud(SimpleNamespace(region="cn-beijing"))
    cloud.call = AsyncMock(return_value={"Id": "gw-new"})
    assert (
        asyncio.run(cloud.create_gateway("managed", "vpc", ["subnet-a", "subnet-c"]))
        == "gw-new"
    )
    cloud.call.assert_awaited_once_with(
        "CreateGateway",
        {
            "Name": "managed",
            "Region": "cn-beijing",
            "Type": "standard",
            "NetworkSpec": {"VpcId": "vpc", "SubnetIds": ["subnet-a", "subnet-c"]},
            "ResourceSpec": {
                "Replicas": 2,
                "InstanceSpecCode": "1c2g",
                "CLBSpecCode": "small_1",
                "PublicNetworkBillingType": "traffic",
                "NetworkType": {
                    "EnablePublicNetwork": True,
                    "EnablePrivateNetwork": True,
                },
            },
        },
    )


@pytest.mark.parametrize("ids", [[], ["one"], ["one", "one"]])
def test_standard_gateway_rejects_insufficient_subnets_before_dispatch(ids):
    cloud = GatewayCloud(SimpleNamespace(region="cn-beijing"))
    cloud.call = AsyncMock()
    with pytest.raises(APIGClientError, match="distinct subnet"):
        asyncio.run(cloud.create_gateway("managed", "vpc", ids))
    cloud.call.assert_not_awaited()


def test_gateway_zones_are_from_apig():
    cloud = GatewayCloud(SimpleNamespace(region="cn-beijing"))
    cloud.call = AsyncMock(
        return_value={"AvailableZones": ["cn-beijing-c", "cn-beijing-a"]}
    )
    assert asyncio.run(cloud.available_zones()) == ["cn-beijing-a", "cn-beijing-c"]
    cloud.call.assert_awaited_once_with("GetGatewayAvailableZones", {})


@pytest.mark.parametrize(
    "zones",
    [
        None,
        [],
        ["cn-beijing-a"],
        ["cn-beijing-a", "cn-shanghai-a"],
        ["cn-beijing-a", "cn-beijing-a"],
        "bad",
    ],
)
def test_invalid_gateway_zones_fail_closed(zones):
    cloud = GatewayCloud(SimpleNamespace(region="cn-beijing"))
    cloud.call = AsyncMock(return_value={"AvailableZones": zones})
    with pytest.raises(APIGClientError, match="available zones"):
        asyncio.run(cloud.available_zones())


def test_gateway_reads_universal_sdk_raw_response_when_decoded_result_is_empty(
    monkeypatch,
):
    import volcenginesdkcore
    from volcenginesdkcore import universal

    credentials = SimpleNamespace(
        access_key_id="fake", secret_access_key="fake", session_token="fake"
    )
    raw = {"Result": {"Gateway": {"Id": "g-one"}}}
    client = SimpleNamespace(
        last_response=SimpleNamespace(data=json.dumps(raw).encode())
    )
    monkeypatch.setattr(volcenginesdkcore, "ApiClient", lambda config: client)
    monkeypatch.setattr(
        universal,
        "UniversalApi",
        lambda value: SimpleNamespace(do_call=lambda *a, **kw: {}),
    )
    cloud = GatewayCloud(
        SimpleNamespace(region="cn-beijing", _credentials=lambda: credentials)
    )
    assert asyncio.run(cloud.get_gateway("g-one")) == {"Id": "g-one"}
