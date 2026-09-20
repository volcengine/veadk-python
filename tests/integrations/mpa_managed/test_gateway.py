import asyncio
import copy
from contextlib import asynccontextmanager
from types import SimpleNamespace
import pytest
from veadk.integrations.mpa.managed.gateway_cloud import APIGClientError
from veadk.integrations.mpa.managed.gateway import SharedAPIGService, SharedGatewayError


class Registry:
    def __init__(self):
        self.rows = {}
        self.locks = {}

    async def initialize(self):
        pass

    async def close(self):
        pass

    @asynccontextmanager
    async def lock(self, account, region):
        key = account, region
        async with self.locks.setdefault(key, asyncio.Lock()):
            yield Entry(self.rows, key)


class Entry:
    def __init__(self, rows, key):
        self.rows, self.key = rows, key

    async def read(self):
        return copy.deepcopy(self.rows.get(self.key, {}))

    async def save(self, row):
        self.rows[self.key] = copy.deepcopy(row)


class Cloud:
    def __init__(self, account="account-1", region="cn-beijing"):
        self.account, self.region = account, region
        self.gateways = {}
        self.created = 0
        self.im_created = 0
        self.im = False
        self.create_error = None
        self.commit_before_error = False
        self.status_error = None

    async def account_id(self):
        return self.account

    async def find_gateways(self, name):
        return [g for g in self.gateways.values() if g["Name"] == name]

    async def create_gateway(self, name, vpc_id, subnet_ids):
        self.created += 1
        if not self.create_error or self.commit_before_error:
            self.gateways["gw-1"] = {
                "Id": "gw-1",
                "Name": name,
                "Type": "serverless",
                "Region": self.region,
                "Status": "Running",
                "NetworkSpec": {"VpcId": vpc_id},
            }
        if self.create_error:
            raise self.create_error
        return "gw-1"

    async def get_gateway(self, gateway_id):
        return self.gateways[gateway_id]

    async def get_im_gateway_service_status(self, **kwargs):
        if self.status_error:
            raise self.status_error
        if not self.im:
            raise APIGClientError("missing", code="ResourceNotFound")
        return SimpleNamespace(
            status="RUNNING",
            im_gateway_endpoint="https://im.example",
            im_gateway_service_id="service-1",
        )

    async def create_im_gateway_service(self, **kwargs):
        self.im_created += 1
        self.im = True

    async def wait_im_gateway_service_ready(self, **kwargs):
        return await self.get_im_gateway_service_status(**kwargs)


def service(registry, cloud, **kwargs):
    return SharedAPIGService(
        registry=registry,
        cloud=cloud,
        region=cloud.region,
        attempts=2,
        interval=0,
        **kwargs,
    )


def test_parallel_runtimes_share_exactly_one_gateway_and_im_service():
    async def scenario():
        registry, cloud = Registry(), Cloud()
        results = await asyncio.gather(
            *[
                service(registry, cloud).ensure(vpc_id="vpc-1", subnet_ids=["subnet-1"])
                for _ in range(8)
            ]
        )
        assert {r["gateway_id"] for r in results} == {"gw-1"}
        assert cloud.created == cloud.im_created == 1
        assert registry.rows[(cloud.account, cloud.region)]["state"] == "ready"
        assert "runtime_api_key" not in str(registry.rows)

    asyncio.run(scenario())


@pytest.mark.parametrize("commit", [True, False])
def test_unknown_create_outcome_never_issues_a_second_create(commit):
    async def scenario():
        registry, cloud = Registry(), Cloud()
        cloud.create_error = TimeoutError()
        cloud.commit_before_error = commit
        with pytest.raises(TimeoutError):
            await service(registry, cloud).ensure(
                vpc_id="vpc-1", subnet_ids=["subnet-1"]
            )
        cloud.create_error = None
        if commit:
            result = await service(registry, cloud).ensure(
                vpc_id="vpc-1", subnet_ids=["subnet-1"]
            )
            assert result["gateway_id"] == "gw-1"
        else:
            with pytest.raises(SharedGatewayError, match="outcome unknown"):
                await service(registry, cloud).ensure(
                    vpc_id="vpc-1", subnet_ids=["subnet-1"]
                )
        assert cloud.created == 1

    asyncio.run(scenario())


def test_definitive_permission_error_can_retry_after_permissions_fixed():
    async def scenario():
        registry, cloud = Registry(), Cloud()
        cloud.create_error = APIGClientError("denied", code="AccessDenied")
        with pytest.raises(APIGClientError):
            await service(registry, cloud).ensure(
                vpc_id="vpc-1", subnet_ids=["subnet-1"]
            )
        assert registry.rows[(cloud.account, cloud.region)]["create_requested"] is False
        cloud.create_error = None
        await service(registry, cloud).ensure(vpc_id="vpc-1", subnet_ids=["subnet-1"])
        assert cloud.created == 2

    asyncio.run(scenario())


@pytest.mark.parametrize("code", ["AccessDenied", "Throttling", "InternalError"])
def test_im_status_errors_do_not_trigger_create(code):
    async def scenario():
        registry, cloud = Registry(), Cloud()
        cloud.status_error = APIGClientError("status failed", code=code)
        with pytest.raises(APIGClientError):
            await service(registry, cloud).ensure(
                vpc_id="vpc-1", subnet_ids=["subnet-1"]
            )
        assert cloud.im_created == 0
        assert registry.rows[(cloud.account, cloud.region)]["gateway_id"] == "gw-1"

    asyncio.run(scenario())


def test_im_unknown_create_retries_status_only():
    async def scenario():
        registry, cloud = Registry(), Cloud()

        async def fail(**kwargs):
            cloud.im_created += 1
            raise TimeoutError()

        cloud.create_im_gateway_service = fail
        with pytest.raises(TimeoutError):
            await service(registry, cloud).ensure(
                vpc_id="vpc-1", subnet_ids=["subnet-1"]
            )
        with pytest.raises(
            SharedGatewayError, match="IM Gateway creation outcome unknown"
        ):
            await service(registry, cloud).ensure(
                vpc_id="vpc-1", subnet_ids=["subnet-1"]
            )
        assert cloud.im_created == 1
        cloud.im = True
        assert (
            await service(registry, cloud).ensure(
                vpc_id="vpc-1", subnet_ids=["subnet-1"]
            )
        )["state"] == "ready"

    asyncio.run(scenario())


def test_account_and_region_are_separate_registry_keys():
    async def scenario():
        registry = Registry()
        for cloud in [Cloud(), Cloud("account-2"), Cloud(region="cn-shanghai")]:
            await service(registry, cloud).ensure(
                vpc_id="vpc-1", subnet_ids=["subnet-1"]
            )
        assert len(registry.rows) == 3

    asyncio.run(scenario())


def test_other_vpc_and_adoption_conflicts_do_not_replace_shared_gateway():
    async def scenario():
        registry, cloud = Registry(), Cloud()
        await service(registry, cloud).ensure(vpc_id="vpc-1", subnet_ids=["subnet-1"])
        for kwargs in [{"vpc_id": "vpc-2"}, {"vpc_id": "vpc-1", "adopt_id": "other"}]:
            with pytest.raises(SharedGatewayError):
                await service(registry, cloud).ensure(subnet_ids=["subnet-1"], **kwargs)
        assert cloud.created == 1
        assert registry.rows[(cloud.account, cloud.region)]["gateway_id"] == "gw-1"

    asyncio.run(scenario())


@pytest.mark.parametrize("gateway_type", ["serverless", "standard"])
def test_adopts_existing_gateway_without_creating_or_deleting(gateway_type):
    async def scenario():
        registry, cloud = Registry(), Cloud()
        cloud.gateways["existing"] = {
            "Id": "existing",
            "Name": "existing-space",
            "Type": gateway_type,
            "Region": cloud.region,
            "Status": "Running",
            "NetworkSpec": {"VpcId": "vpc-1"},
        }
        result = await service(registry, cloud).ensure(
            vpc_id="vpc-1", subnet_ids=["subnet-1"], adopt_id="existing"
        )
        assert result["gateway_id"] == "existing"
        assert cloud.created == 0

    asyncio.run(scenario())
