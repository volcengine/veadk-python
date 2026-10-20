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

"""SDK requests, rotating credentials, safe errors and paginated discovery."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from veadk.integrations.mpa.managed.database import DeploymentError
from veadk.integrations.mpa.managed.network_cloud import NetworkCloud, NetworkCloudError


def test_sdk_requests_use_verified_rotating_credentials_and_region(monkeypatch):
    import volcenginesdkcore
    import volcenginesdkecs
    import volcenginesdkvpc

    seen = []
    sequence = iter(["first", "second", "third", "fourth", "fifth"])

    def credentials():
        return SimpleNamespace(
            access_key_id=next(sequence),
            secret_access_key="private",
            session_token="sts",
        )

    monkeypatch.setattr(volcenginesdkcore, "ApiClient", lambda c: c)

    class Client:
        def __init__(self, config):
            self.config = config

        def __getattr__(self, method):
            def invoke(request, **kw):
                assert kw["_request_timeout"] == 30
                assert self.config.session_token == "sts"
                seen.append(
                    (method, self.config.ak, self.config.host, request.to_dict())
                )
                return SimpleNamespace(
                    to_dict=lambda: {
                        "vpc_id": "vpc",
                        "subnet_id": "subnet",
                        "zones": [{"zone_id": "cn-beijing-a"}],
                    }
                )

            return invoke

    monkeypatch.setattr(volcenginesdkvpc, "VPCApi", Client)
    monkeypatch.setattr(volcenginesdkecs, "ECSApi", Client)
    cloud = NetworkCloud(region="cn-beijing", credentials=credentials)

    async def run():
        assert (
            await cloud.create_vpc(
                {"cidr_block": "172.20.0.0/16", "client_token": "vpc-token"}
            )
            == "vpc"
        )
        assert (
            await cloud.create_subnet(
                {
                    "vpc_id": "vpc",
                    "cidr_block": "172.20.0.0/24",
                    "zone_id": "cn-beijing-a",
                    "client_token": "subnet-token",
                }
            )
            == "subnet"
        )
        await cloud.vpc("vpc")
        await cloud.subnet("subnet")
        assert await cloud.zones() == ["cn-beijing-a"]
        assert [x[1] for x in seen] == ["first", "second", "third", "fourth", "fifth"]
        assert seen[0][2] == "vpc.cn-beijing.volcengineapi.com"
        assert seen[-1][2] == "ecs.cn-beijing.volcengineapi.com"
        assert seen[0][3]["client_token"] == "vpc-token"
        assert seen[1][3]["zone_id"] == "cn-beijing-a"

    asyncio.run(run())


@pytest.mark.parametrize(
    "body,code",
    [
        ('{"ResponseMetadata":{"Error":{"Code":"AccessDenied"}}}', "AccessDenied"),
        ("private raw error", "CloudRequestFailed"),
        (
            '{"ResponseMetadata":{"Error":{"Code":"secret value"}}}',
            "CloudRequestFailed",
        ),
    ],
)
def test_sdk_errors_do_not_expose_credentials_or_response_bodies(body, code):
    class SDKError(RuntimeError):
        def __init__(self, body: str):
            super().__init__("private secret")
            self.body = body

    def credentials():
        raise SDKError(body)

    cloud = NetworkCloud(region="r", credentials=credentials)
    with pytest.raises(NetworkCloudError) as exc:
        asyncio.run(cloud.vpc("vpc"))
    assert exc.value.code == code
    assert "secret" not in str(exc.value) and "private" not in str(exc.value)


def test_account_drift_error_is_not_hidden():
    def credentials():
        raise DeploymentError("Cloud credentials changed accounts")

    with pytest.raises(DeploymentError, match="changed accounts"):
        asyncio.run(NetworkCloud(region="r", credentials=credentials).zones())


def test_network_discovery_paginates_and_filters_exact_names():
    async def run():
        cloud = NetworkCloud(region="r", credentials=None)
        cloud.call = AsyncMock(
            side_effect=[
                {"vpcs": [{"vpc_name": "prefix-match"}] * 100},
                {"vpcs": [{"vpc_name": "exact", "vpc_id": "one"}]},
            ]
        )
        assert await cloud.find_vpcs("exact") == [
            {"vpc_name": "exact", "vpc_id": "one"}
        ]
        assert cloud.call.call_args.kwargs["page_number"] == 2
        cloud.call = AsyncMock(return_value={"subnets": []})
        assert await cloud.subnets("vpc") == []
        assert cloud.call.call_args.kwargs["vpc_id"] == "vpc"

    asyncio.run(run())


@pytest.mark.parametrize("collection", ["vpcs", "subnets"])
@pytest.mark.parametrize("serialization", ["sdk", "absent"])
def test_discovery_accepts_confirmed_empty_sdk_results(collection, serialization):
    import volcenginesdkvpc

    response_type = (
        volcenginesdkvpc.DescribeVpcsResponse
        if collection == "vpcs"
        else volcenginesdkvpc.DescribeSubnetsResponse
    )
    response = response_type(total_count=0).to_dict()
    assert response[collection] is None
    if serialization == "absent":
        del response[collection]
    cloud = NetworkCloud(region="r", credentials=None)
    cloud.call = AsyncMock(return_value=response)
    discover = cloud.find_vpcs if collection == "vpcs" else cloud.subnets
    assert asyncio.run(discover("name-or-vpc")) == []
    cloud.call.assert_awaited_once()
    assert cloud.call.call_args.kwargs["page_number"] == 1


@pytest.mark.parametrize("collection", ["vpcs", "subnets"])
@pytest.mark.parametrize(
    "response",
    [
        {},
        {"total_count": 1},
        {"total_count": -1},
        {"total_count": None},
        {"total_count": False},
        {"total_count": "0"},
        {"total_count": 0.0},
        {"items": "", "total_count": 0},
        {"items": {}, "total_count": 0},
    ],
)
def test_discovery_rejects_unconfirmed_or_malformed_empty_results(collection, response):
    payload = {**response, collection: response.get("items")}
    cloud = NetworkCloud(region="r", credentials=None)
    cloud.call = AsyncMock(return_value=payload)
    discover = cloud.find_vpcs if collection == "vpcs" else cloud.subnets
    with pytest.raises(DeploymentError, match="invalid results"):
        asyncio.run(discover("name-or-vpc"))
    cloud.call.assert_awaited_once()


@pytest.mark.parametrize("collection", ["vpcs", "subnets"])
def test_discovery_rejects_null_zero_page_after_populated_page(collection):
    cloud = NetworkCloud(region="r", credentials=None)
    cloud.call = AsyncMock(
        side_effect=[
            {collection: [{}] * 100, "total_count": 100},
            {collection: None, "total_count": 0},
        ]
    )
    discover = cloud.find_vpcs if collection == "vpcs" else cloud.subnets
    with pytest.raises(DeploymentError, match="invalid results"):
        asyncio.run(discover("name-or-vpc"))
    assert cloud.call.await_count == 2


def test_empty_discovery_does_not_hide_provider_errors():
    cloud = NetworkCloud(region="r", credentials=None)
    cloud.call = AsyncMock(
        side_effect=NetworkCloudError("describe_subnets", "AccessDenied")
    )
    with pytest.raises(NetworkCloudError, match="AccessDenied"):
        asyncio.run(cloud.subnets("vpc"))


@pytest.mark.parametrize(
    "method,args,message",
    [
        ("create_vpc", ({},), "no ID"),
        ("create_subnet", ({},), "no ID"),
        ("zones", (), "No available"),
        ("find_vpcs", ("name",), "invalid results"),
    ],
)
def test_incomplete_cloud_responses_fail_closed(method, args, message):
    cloud = NetworkCloud(region="r", credentials=None)
    cloud.call = AsyncMock(return_value={})
    with pytest.raises(DeploymentError, match=message):
        asyncio.run(getattr(cloud, method)(*args))


def test_discovery_stops_on_invalid_pagination():
    cloud = NetworkCloud(region="r", credentials=None)
    cloud.call = AsyncMock(return_value={"vpcs": [{}] * 100})
    with pytest.raises(DeploymentError, match="pagination"):
        asyncio.run(cloud.find_vpcs("name"))
