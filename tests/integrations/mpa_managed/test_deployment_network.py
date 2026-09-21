"""Fresh-account networking, adoption, drift and durable recovery contracts."""

import asyncio
import copy
from unittest.mock import AsyncMock

import pytest

from veadk.integrations.mpa.managed.database import DeploymentError
from veadk.integrations.mpa.managed.network import (
    AccountNetworkProvisioner,
    NetworkOptions,
)
from veadk.integrations.mpa.managed.network_cloud import NetworkCloudError
from tests.integrations.mpa_managed.fakes_deployment_network import (
    NetworkCloud,
    NetworkEntry,
)


def provisioner(cloud=None, **kw):
    return AccountNetworkProvisioner(
        cloud=cloud or NetworkCloud(),
        account="account",
        region="cn-beijing",
        interval=0,
        timeout=0.02,
        **kw,
    )


def test_fresh_account_creates_once_and_other_agents_reuse_network():
    async def run():
        entry, cloud = NetworkEntry(), NetworkCloud()
        service = provisioner(cloud)
        first = await service.ensure(entry)
        second = await service.ensure(entry)
        assert first == second
        assert first == {
            "EnablePublicNetwork": True,
            "EnablePrivateNetwork": True,
            "VpcConfiguration": {
                "VpcId": "vpc-auto",
                "SubnetIds": ["subnet-auto"],
                "EnableSharedInternetAccess": True,
            },
        }
        assert [c[0] for c in cloud.calls] == ["vpc", "subnet"]
        assert entry.row["state"] == "ready"
        for kind, request in cloud.calls:
            assert request["client_token"]
            assert "test" not in request[kind + "_name"]
            assert any(
                r.get(kind + "_dispatched") and r.get(kind + "_request") == request
                for r in entry.saved
            )

    asyncio.run(run())


@pytest.mark.parametrize("kind", ["vpc", "subnet"])
def test_lost_response_discovers_resource_without_duplicate_create(kind):
    async def run():
        entry, cloud = NetworkEntry(), NetworkCloud()
        cloud.lose = kind
        with pytest.raises(TimeoutError):
            await provisioner(cloud).ensure(entry)
        cloud.hide = True
        with pytest.raises(DeploymentError, match="outcome unknown"):
            await provisioner(cloud).ensure(entry)
        cloud.hide = False
        await provisioner(cloud).ensure(entry)
        assert [c[0] for c in cloud.calls] == ["vpc", "subnet"]

    asyncio.run(run())


@pytest.mark.parametrize("source", ["explicit", "gateway", "registered"])
def test_existing_network_is_adopted_without_creating_resources(source):
    async def run():
        entry, cloud = NetworkEntry(), NetworkCloud(existing=True)
        request = None
        if source == "explicit":
            request = {
                "VpcConfiguration": {
                    "VpcId": "vpc-one",
                    "SubnetIds": ["subnet-one"],
                    "EnableSharedInternetAccess": False,
                }
            }
        elif source == "gateway":
            entry.gateway_row = {"vpc_id": "vpc-one", "gateway_id": "gateway-one"}
        else:
            entry.row = {"vpc_id": "vpc-one", "subnet_ids": ["subnet-one"]}
        result = await provisioner(cloud).ensure(entry, request)
        assert result["VpcConfiguration"]["VpcId"] == "vpc-one"
        assert result["VpcConfiguration"]["SubnetIds"] == ["subnet-one"]
        assert result["VpcConfiguration"]["EnableSharedInternetAccess"] == (
            source != "explicit"
        )
        assert not cloud.calls

    asyncio.run(run())


def test_shared_gateway_vpc_without_available_subnet_allocates_nonoverlapping_cidr():
    async def run():
        entry, cloud = NetworkEntry(), NetworkCloud(existing=True)
        entry.gateway_row = {"vpc_id": "vpc-one", "gateway_id": "gw"}
        cloud.subnet_rows["subnet-one"]["available_ip_address_count"] = 0
        result = await provisioner(cloud).ensure(entry)
        assert result["VpcConfiguration"]["VpcId"] == "vpc-one"
        assert cloud.calls[0][0] == "subnet"
        assert cloud.calls[0][1]["cidr_block"] == "172.20.1.0/24"

    asyncio.run(run())


def test_explicit_vpc_conflicting_with_gateway_never_creates_or_updates_registry():
    async def run():
        entry, cloud = NetworkEntry(), NetworkCloud(existing=True)
        entry.gateway_row = {"vpc_id": "vpc-other"}
        with pytest.raises(DeploymentError, match="shared APIG"):
            await provisioner(cloud).ensure(
                entry, {"VpcConfiguration": {"VpcId": "vpc-one"}}
            )
        assert not cloud.calls and not entry.saved

    asyncio.run(run())


@pytest.mark.parametrize(
    "mutation,error",
    [
        ({"vpc_id": "vpc-other"}, "outside"),
        ({"account_id": "other"}, "account"),
        ({"status": "Deleting"}, "unavailable"),
        ({"available_ip_address_count": 0}, "available IP"),
        ({"zone_id": "cn-shanghai-a"}, "region"),
    ],
)
def test_pinned_subnet_is_validated_and_never_silently_replaced(mutation, error):
    async def run():
        entry, cloud = NetworkEntry(), NetworkCloud(existing=True)
        entry.row = {"vpc_id": "vpc-one", "subnet_ids": ["subnet-one"]}
        cloud.subnet_rows["subnet-one"].update(mutation)
        with pytest.raises(DeploymentError, match=error):
            await provisioner(cloud).ensure(entry)
        assert not cloud.calls

    asyncio.run(run())


def test_managed_name_collision_and_duplicate_names_are_rejected():
    async def run():
        entry, cloud = NetworkEntry(), NetworkCloud()
        service = provisioner(cloud)
        cloud.vpcs["vpc-other"] = {
            **cloud.vpc_row("vpc-other"),
            "vpc_name": service.name,
            "description": "unrelated",
        }
        with pytest.raises(DeploymentError, match="ownership"):
            await service.ensure(entry)
        cloud.vpcs["vpc-third"] = copy.deepcopy(cloud.vpcs["vpc-other"])
        with pytest.raises(DeploymentError, match="Multiple"):
            await service.ensure(entry)
        assert not cloud.calls

    asyncio.run(run())


def test_managed_resources_can_be_recovered_by_name_after_registry_loss():
    async def run():
        cloud = NetworkCloud()
        service = provisioner(cloud)
        expected = await service.ensure(NetworkEntry())
        assert await service.ensure(NetworkEntry()) == expected
        assert len(cloud.calls) == 2

    asyncio.run(run())


@pytest.mark.parametrize("kind", ["vpc", "subnet"])
def test_pending_network_waits_and_can_resume(kind):
    async def run():
        entry, cloud = NetworkEntry(), NetworkCloud()
        await provisioner(cloud).ensure(entry)
        rows = cloud.vpcs if kind == "vpc" else cloud.subnet_rows
        rows[kind + "-auto"]["status"] = "Pending"
        with pytest.raises(DeploymentError, match="still creating"):
            await provisioner(cloud).ensure(entry)
        rows[kind + "-auto"]["status"] = "Available"
        await provisioner(cloud).ensure(entry)
        assert len(cloud.calls) == 2

    asyncio.run(run())


def test_definite_permission_rejection_can_retry_with_same_token():
    async def run():
        entry, cloud = NetworkEntry(), NetworkCloud()
        create = cloud.create_vpc
        cloud.create_vpc = AsyncMock(
            side_effect=NetworkCloudError("CreateVpc", "AccessDenied")
        )
        with pytest.raises(NetworkCloudError):
            await provisioner(cloud).ensure(entry)
        token = entry.row["vpc_request"]["client_token"]
        assert not entry.row["vpc_dispatched"]
        cloud.create_vpc = create
        await provisioner(cloud).ensure(entry)
        assert cloud.calls[0][1]["client_token"] == token

    asyncio.run(run())


def test_custom_cidr_zone_and_changed_pending_request():
    async def run():
        entry, cloud = NetworkEntry(), NetworkCloud()
        options = NetworkOptions(vpc_cidr="10.80.0.0/16", zone_id="cn-beijing-b")
        cloud.lose = "subnet"
        with pytest.raises(TimeoutError):
            await provisioner(cloud, options=options).ensure(entry)
        with pytest.raises(DeploymentError, match="different inputs"):
            await provisioner(
                cloud, options=NetworkOptions(zone_id="cn-beijing-a")
            ).ensure(entry)
        await provisioner(cloud, options=options).ensure(entry)
        assert cloud.calls[0][1]["cidr_block"] == "10.80.0.0/16"
        assert cloud.calls[1][1]["zone_id"] == "cn-beijing-b"
        # Creation CIDR is not required again for subsequent agents.
        await provisioner(cloud).ensure(entry)

    asyncio.run(run())


def test_current_public_only_runtime_requires_migration_before_network_writes():
    async def run():
        entry, cloud = NetworkEntry(), NetworkCloud()
        with pytest.raises(DeploymentError, match="migration"):
            await provisioner(cloud).ensure(
                entry, current={"NetworkConfigurations": [{"NetworkType": "public"}]}
            )
        assert not cloud.calls and not entry.saved

    asyncio.run(run())


@pytest.mark.parametrize(
    "options",
    [
        NetworkOptions(vpc_cidr="8.8.0.0/16"),
        NetworkOptions(vpc_cidr="bad"),
        NetworkOptions(subnet_prefix=30),
        NetworkOptions(subnet_prefix=16),
    ],
)
def test_invalid_creation_parameters_fail_before_cloud_calls(options):
    with pytest.raises(DeploymentError, match="IPv4"):
        provisioner(options=options)


@pytest.mark.parametrize(
    "network_request",
    [
        {"EnablePublicNetwork": False},
        {"EnablePrivateNetwork": False, "VpcConfiguration": {"VpcId": "vpc-one"}},
        {"VpcConfiguration": {"SubnetIds": ["subnet-one"]}},
    ],
)
def test_incomplete_network_request_never_changes_resources(network_request):
    async def run():
        entry, cloud = NetworkEntry(), NetworkCloud()
        with pytest.raises(DeploymentError):
            await provisioner(cloud).ensure(entry, network_request)
        assert not cloud.calls and not entry.saved

    asyncio.run(run())


def test_explicit_subnet_override_preserves_account_default_and_rejects_runtime_migration():
    async def run():
        entry, cloud = NetworkEntry(), NetworkCloud(existing=True)
        service = provisioner(cloud)
        await service.ensure(entry, {"VpcConfiguration": {"VpcId": "vpc-one"}})
        cloud.subnet_rows["subnet-two"] = cloud.subnet_row("subnet-two", "vpc-one")
        request = {
            "VpcConfiguration": {"VpcId": "vpc-one", "SubnetIds": ["subnet-two"]}
        }
        result = await service.ensure(entry, request)
        assert result["VpcConfiguration"]["SubnetIds"] == ["subnet-two"]
        assert entry.row["subnet_ids"] == ["subnet-one"]
        current = {
            "NetworkConfigurations": [
                {"NetworkType": "public"},
                {
                    "NetworkType": "private",
                    "VpcConfiguration": {
                        "VpcId": "vpc-one",
                        "SubnetIds": ["subnet-one"],
                    },
                },
            ]
        }
        with pytest.raises(DeploymentError, match="migration"):
            await service.ensure(entry, request, current=current)
        with pytest.raises(DeploymentError, match="distinct"):
            await service.ensure(
                entry,
                {
                    "VpcConfiguration": {
                        "VpcId": "vpc-one",
                        "SubnetIds": ["subnet-one", "subnet-one"],
                    }
                },
            )
        assert not cloud.calls

    asyncio.run(run())


def test_changed_managed_vpc_or_unavailable_zone_never_creates_replacements():
    async def run():
        entry, cloud = NetworkEntry(), NetworkCloud()
        await provisioner(cloud).ensure(entry)
        cloud.vpcs["vpc-auto"]["description"] = "changed"
        with pytest.raises(DeploymentError, match="ownership"):
            await provisioner(cloud).ensure(entry)
        assert len(cloud.calls) == 2
        cloud = NetworkCloud(existing=True)
        with pytest.raises(DeploymentError, match="zone"):
            await provisioner(
                cloud, options=NetworkOptions(zone_id="wrong-zone")
            ).ensure(NetworkEntry(), {"VpcConfiguration": {"VpcId": "vpc-one"}})
        assert not cloud.calls

    asyncio.run(run())


def test_exhausted_cidr_and_changed_pending_subnet_prefix_fail_without_duplicate_create():
    async def run():
        entry, cloud = NetworkEntry(), NetworkCloud(existing=True)
        cloud.vpcs["vpc-one"]["cidr_block"] = "172.20.0.0/24"
        cloud.subnet_rows["subnet-one"]["available_ip_address_count"] = 0
        with pytest.raises(DeploymentError, match="No free subnet CIDR"):
            await provisioner(cloud).ensure(
                entry, {"VpcConfiguration": {"VpcId": "vpc-one"}}
            )
        assert not cloud.calls
        entry, cloud = NetworkEntry(), NetworkCloud()
        cloud.lose = "subnet"
        with pytest.raises(TimeoutError):
            await provisioner(cloud).ensure(entry)
        with pytest.raises(DeploymentError, match="different prefix"):
            await provisioner(cloud, options=NetworkOptions(subnet_prefix=25)).ensure(
                entry
            )
        assert len(cloud.calls) == 2

    asyncio.run(run())


@pytest.mark.parametrize(
    "cidr", ["10.0.0.0/8", "10.128.0.0/9", "172.16.0.0/12", "192.168.0.0/16"]
)
def test_rfc1918_private_network_ranges(cidr):
    NetworkOptions(vpc_cidr=cidr, subnet_prefix=24).validate()


@pytest.mark.parametrize(
    "cidr", ["10.0.0.0/7", "11.0.0.0/8", "172.0.0.0/12", "192.0.0.0/24", "127.0.0.0/8"]
)
def test_non_rfc1918_network_ranges_rejected(cidr):
    with pytest.raises(DeploymentError):
        NetworkOptions(vpc_cidr=cidr, subnet_prefix=25).validate()
