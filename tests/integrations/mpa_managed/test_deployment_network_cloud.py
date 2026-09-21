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
