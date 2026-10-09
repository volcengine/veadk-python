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

"""Fresh-account networking, adoption, drift and durable recovery contracts."""

import asyncio
import copy
from unittest.mock import AsyncMock

import pytest

from veadk.integrations.mpa.managed.database import DeploymentError
from veadk.integrations.mpa.managed.network import (
    AccountNetworkProvisioner,
    NetworkOptions,
    same_subnet_ids,
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


@pytest.mark.parametrize(
    "selection",
    [
        [],
        None,
        "subnet-one",
        ["subnet-one", "subnet-one"],
        ["subnet-one", None],
        ["subnet-one", []],
        ["subnet-one", ""],
        ["subnet-one", " "],
        [f"subnet-{i}" for i in range(6)],
    ],
)
def test_equal_invalid_subnet_selections_do_not_hide_invalid_inputs(selection):
    assert not same_subnet_ids(selection, selection)


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


def test_recorded_vpc_with_null_empty_sdk_subnets_resumes_without_new_vpc():
    from veadk.integrations.mpa.managed.network_cloud import NetworkCloud as SDKCloud

    async def run():
        entry, cloud = NetworkEntry(), NetworkCloud()
        service = provisioner(cloud)
        cloud.vpcs["vpc-recorded"] = {
            **cloud.vpc_row("vpc-recorded"),
            "description": service.marker,
        }
        entry.row.update(
            vpc_id="vpc-recorded",
            managed_vpc=True,
            vpc_request={"cidr_block": "172.20.0.0/16"},
        )
        original_subnets = cloud.subnets
        adapter = SDKCloud(region="cn-beijing", credentials=None)

        async def sdk_response(method, request_type, **params):
            assert method == "describe_subnets"
            assert request_type == "DescribeSubnetsRequest"
            rows = await original_subnets(params["vpc_id"])
            return {"subnets": rows or None, "total_count": len(rows)}

        adapter.call = AsyncMock(side_effect=sdk_response)

        async def subnets(vid):
            return await adapter.subnets(vid)

        cloud.subnets = subnets
        first = await service.ensure(entry)
        assert first == await service.ensure(entry)
        assert first["VpcConfiguration"]["VpcId"] == "vpc-recorded"
        assert first["VpcConfiguration"]["SubnetIds"] == ["subnet-auto"]
        assert [kind for kind, _ in cloud.calls] == ["subnet"]
        assert entry.row["state"] == "ready"

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


@pytest.mark.parametrize("selection", ["explicit", "registered", "different-default"])
def test_current_subnet_permutation_preserves_stable_selection(selection):
    async def run():
        entry, cloud = NetworkEntry(), NetworkCloud(existing=True)
        original = ["subnet-one", "subnet-two"]
        cloud.subnet_rows["subnet-two"] = cloud.subnet_row("subnet-two", "vpc-one")
        cloud.subnet_rows["subnet-two"]["zone_id"] = "cn-beijing-b"
        entry.row = {
            "vpc_id": "vpc-one",
            "subnet_ids": original
            if selection != "different-default"
            else ["subnet-one"],
            "state": "ready",
        }
        request = (
            {"VpcConfiguration": {"VpcId": "vpc-one", "SubnetIds": original}}
            if selection == "explicit"
            else None
        )
        current = {
            "NetworkConfigurations": [
                {"NetworkType": "public"},
                {
                    "NetworkType": "private",
                    "VpcConfiguration": {
                        "VpcId": "vpc-one",
                        "SubnetIds": list(reversed(original)),
                        "EnableSharedInternetAccess": True,
                    },
                },
            ]
        }
        before = copy.deepcopy((entry.row, request, current))
        result = await provisioner(cloud).ensure(entry, request, current=current)
        assert result["VpcConfiguration"]["SubnetIds"] == (
            list(reversed(original)) if selection == "different-default" else original
        )
        assert (entry.row, request, current) == before
        assert not cloud.calls

    asyncio.run(run())


@pytest.mark.parametrize(
    "field,value",
    [
        ("VpcId", "vpc-other"),
        ("EnableSharedInternetAccess", False),
        ("SubnetIds", ["subnet-one"]),
        ("SubnetIds", ["subnet-one", "subnet-other"]),
        ("SubnetIds", ["subnet-one", "subnet-two", "subnet-other"]),
        ("SubnetIds", ["subnet-one", "subnet-two", "subnet-two"]),
        ("SubnetIds", "subnet-one"),
        ("SubnetIds", ["subnet-one", None]),
    ],
)
def test_current_network_drift_is_rejected_before_resource_writes(field, value):
    async def run():
        entry, cloud = NetworkEntry(), NetworkCloud(existing=True)
        active = {
            "VpcId": "vpc-one",
            "SubnetIds": ["subnet-one", "subnet-two"],
            "EnableSharedInternetAccess": True,
        }
        current = {
            "NetworkConfigurations": [
                {"NetworkType": "public"},
                {"NetworkType": "private", "VpcConfiguration": active},
            ]
        }
        with pytest.raises(DeploymentError, match="migration"):
            await provisioner(cloud).ensure(
                entry, {"VpcConfiguration": {**active, field: value}}, current=current
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


def legacy_request(service, kind):
    marker = service.marker.replace("-v1-", ":v1:")
    if kind == "vpc":
        return dict(
            cidr_block="172.20.0.0/16",
            vpc_name=service.name,
            description=marker,
            project_name="default",
        )
    return dict(
        vpc_id="vpc-one",
        zone_id="cn-beijing-a",
        cidr_block="172.20.0.0/24",
        subnet_name=service.name + "-subnet",
        description=marker,
    )


def enforce_description_format(cloud, entry):
    import re

    for kind in ["vpc", "subnet"]:
        create = getattr(cloud, "create_" + kind)

        async def checked(request, kind=kind, create=create):
            if not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9 _,.=\-]{0,254}", request["description"]
            ):
                raise NetworkCloudError("Create" + kind, "InvalidDescription.Malformed")
            assert entry.row[kind + "_request"] == request
            assert entry.row[kind + "_dispatched"] is True
            return await create(request)

        setattr(cloud, "create_" + kind, checked)


@pytest.mark.asyncio
async def test_new_network_descriptions_pass_provider_format_and_reuse():
    entry, cloud = NetworkEntry(), NetworkCloud()
    enforce_description_format(cloud, entry)
    service = provisioner(cloud)
    expected = await service.ensure(entry)
    assert await service.ensure(entry) == expected
    assert [kind for kind, request in cloud.calls] == ["vpc", "subnet"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["vpc", "subnet"])
async def test_rejected_legacy_description_resumes_with_new_token(kind):
    entry, cloud = NetworkEntry(), NetworkCloud(existing=kind == "subnet")
    service = provisioner(cloud)
    old = legacy_request(service, kind)
    entry.row = {
        kind + "_request": {**old, "client_token": "old-token"},
        kind + "_dispatched": False,
    }
    if kind == "subnet":
        entry.row["vpc_id"] = "vpc-one"
        cloud.subnet_rows.clear()
    enforce_description_format(cloud, entry)
    await service.ensure(entry)
    request = next(request for target, request in cloud.calls if target == kind)
    assert request["description"] == service.marker
    assert ":" not in request["description"]
    assert request["client_token"] != "old-token"
    assert {
        k: v for k, v in request.items() if k not in ["description", "client_token"]
    } == {k: v for k, v in old.items() if k != "description"}
    assert sum(target == kind for target, request in cloud.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["vpc", "subnet"])
@pytest.mark.parametrize("dispatched", [True, None])
async def test_unknown_legacy_description_never_dispatches_without_discovery(
    kind, dispatched
):
    entry, cloud = NetworkEntry(), NetworkCloud(existing=kind == "subnet")
    service = provisioner(cloud)
    old = legacy_request(service, kind)
    entry.row.update({kind + "_request": {**old, "client_token": "old-token"}})
    if dispatched is not None:
        entry.row[kind + "_dispatched"] = dispatched
    if kind == "subnet":
        entry.row["vpc_id"] = "vpc-one"
        cloud.subnet_rows.clear()
    with pytest.raises(DeploymentError):
        await service.ensure(entry)
    assert not cloud.calls
    assert entry.row[kind + "_request"] == {**old, "client_token": "old-token"}
    assert entry.row.get(kind + "_dispatched") is dispatched


@pytest.mark.asyncio
@pytest.mark.parametrize("registered", [False, True])
async def test_old_scoped_network_is_reused_without_mutation(registered):
    cloud = NetworkCloud()
    entry = NetworkEntry()
    service = provisioner(cloud)
    result = await service.ensure(entry)
    old_marker = legacy_request(service, "vpc")["description"]
    cloud.vpcs["vpc-auto"]["description"] = old_marker
    cloud.subnet_rows["subnet-auto"]["description"] = old_marker
    entry.row["vpc_request"]["description"] = old_marker
    entry.row["subnet_request"]["description"] = old_marker
    cloud.calls.clear()
    assert await service.ensure(entry if registered else NetworkEntry()) == result
    assert not cloud.calls
    assert cloud.vpcs["vpc-auto"]["description"] == old_marker


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["vpc", "subnet"])
async def test_unknown_legacy_intent_can_recover_discovered_resource(kind):
    cloud, entry = NetworkCloud(existing=kind == "subnet"), NetworkEntry()
    service = provisioner(cloud)
    old = legacy_request(service, kind)
    if kind == "subnet":
        cloud.subnet_rows.clear()
    await getattr(cloud, "create_" + kind)({**old, "client_token": "old-token"})
    entry.row = {
        kind + "_request": {**old, "client_token": "old-token"},
        kind + "_dispatched": True,
    }
    if kind == "subnet":
        entry.row["vpc_id"] = "vpc-one"
    await service.ensure(entry)
    assert sum(target == kind for target, request in cloud.calls) == 1
    assert entry.row[kind + "_request"]["client_token"] == "old-token"


@pytest.mark.asyncio
async def test_rejected_legacy_request_cannot_change_other_inputs():
    cloud, entry = NetworkCloud(), NetworkEntry()
    service = provisioner(cloud)
    old = legacy_request(service, "vpc")
    old["project_name"] = "other-project"
    entry.row = {
        "vpc_request": {**old, "client_token": "old-token"},
        "vpc_dispatched": False,
    }
    with pytest.raises(DeploymentError, match="different inputs"):
        await service.ensure(entry)
    assert not cloud.calls
    assert entry.row["vpc_request"] == {**old, "client_token": "old-token"}


@pytest.mark.asyncio
async def test_gateway_companion_uses_apig_zones_and_preserves_primary_intent():
    entry, cloud = NetworkEntry(), NetworkCloud()
    manager = provisioner(cloud)
    network = await manager.ensure(entry)
    original = copy.deepcopy(network)
    primary = copy.deepcopy(entry.row["subnet_request"])
    first = await manager.gateway_network(
        entry, network, ["cn-beijing-a", "cn-beijing-c"]
    )
    second = await manager.gateway_network(
        entry, first, ["cn-beijing-a", "cn-beijing-c"]
    )
    assert first == second
    assert network == original
    assert entry.row["subnet_request"] == primary
    assert first["VpcConfiguration"]["SubnetIds"] == ["subnet-auto", "subnet-auto-2"]
    assert [kind for kind, _ in cloud.calls] == ["vpc", "subnet", "subnet"]
    companion = cloud.calls[-1][1]
    assert companion["zone_id"] == "cn-beijing-c"
    assert companion["cidr_block"] == "172.20.1.0/24"
    assert (
        entry.row["gateway_subnet_intents"]["cn-beijing-c"]["subnet_request"]
        == companion
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_gateway_companion_lost_response_discovers_without_duplicate(cancel):
    entry, cloud = NetworkEntry(), NetworkCloud(existing=True)
    entry.row = {"vpc_id": "vpc-one", "subnet_ids": ["subnet-one"]}
    manager = provisioner(cloud)
    network = await manager.ensure(entry)
    create = cloud.create_subnet

    async def lost(request):
        await create(request)
        raise asyncio.CancelledError() if cancel else TimeoutError("lost response")

    cloud.create_subnet = lost
    with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
        await manager.gateway_network(entry, network, ["cn-beijing-a", "cn-beijing-c"])
    cloud.hide = True
    with pytest.raises(DeploymentError, match="outcome unknown"):
        await manager.gateway_network(entry, network, ["cn-beijing-a", "cn-beijing-c"])
    assert len(cloud.calls) == 1
    cloud.hide = False
    result = await manager.gateway_network(
        entry, network, ["cn-beijing-a", "cn-beijing-c"]
    )
    assert result["VpcConfiguration"]["SubnetIds"] == ["subnet-one", "subnet-auto"]
    assert len(cloud.calls) == 1


@pytest.mark.asyncio
async def test_pending_companion_cannot_be_bypassed_by_another_subnet():
    entry, cloud = NetworkEntry(), NetworkCloud(existing=True)
    entry.row = {"vpc_id": "vpc-one", "subnet_ids": ["subnet-one"]}
    manager = provisioner(cloud)
    network = await manager.ensure(entry)
    cloud.lose = "subnet"
    with pytest.raises(TimeoutError):
        await manager.gateway_network(entry, network, ["cn-beijing-a", "cn-beijing-c"])
    cloud.subnet_rows.pop("subnet-auto")
    cloud.subnet_rows["unrelated"] = {
        **cloud.subnet_row("unrelated", "vpc-one"),
        "zone_id": "cn-beijing-c",
    }
    with pytest.raises(DeploymentError, match="outcome unknown"):
        await manager.gateway_network(entry, network, ["cn-beijing-a", "cn-beijing-c"])
    assert len(cloud.calls) == 1


@pytest.mark.asyncio
async def test_existing_cross_zone_subnets_are_reused():
    entry, cloud = NetworkEntry(), NetworkCloud(existing=True)
    entry.row = {"vpc_id": "vpc-one", "subnet_ids": ["subnet-one"]}
    cloud.subnet_rows["subnet-c"] = {
        **cloud.subnet_row("subnet-c", "vpc-one"),
        "zone_id": "cn-beijing-c",
        "cidr_block": "172.20.1.0/24",
    }
    manager = provisioner(cloud)
    network = await manager.ensure(entry)
    result = await manager.gateway_network(
        entry, network, ["cn-beijing-a", "cn-beijing-c"]
    )
    assert result["VpcConfiguration"]["SubnetIds"] == ["subnet-one", "subnet-c"]
    assert cloud.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "zones",
    [
        [],
        ["cn-beijing-a"],
        ["cn-beijing-a", "cn-beijing-a"],
        ["cn-beijing-a", "cn-shanghai-a"],
    ],
)
async def test_gateway_invalid_zones_fail_before_creating_companions(zones):
    entry, cloud = NetworkEntry(), NetworkCloud(existing=True)
    entry.row = {"vpc_id": "vpc-one", "subnet_ids": ["subnet-one"]}
    manager = provisioner(cloud)
    network = await manager.ensure(entry)
    with pytest.raises(DeploymentError, match="APIG"):
        await manager.gateway_network(entry, network, zones)
    assert cloud.calls == []


@pytest.mark.asyncio
async def test_gateway_companion_has_no_free_cidr():
    entry, cloud = NetworkEntry(), NetworkCloud(existing=True)
    entry.row = {"vpc_id": "vpc-one", "subnet_ids": ["subnet-one"]}
    cloud.vpcs["vpc-one"]["cidr_block"] = "172.20.0.0/24"
    manager = provisioner(cloud)
    network = await manager.ensure(entry)
    with pytest.raises(DeploymentError, match="No free subnet CIDR"):
        await manager.gateway_network(entry, network, ["cn-beijing-a", "cn-beijing-c"])
    assert cloud.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("description", "foreign-owner"),
        ("zone_id", "cn-beijing-d"),
        ("account_id", "another-account"),
        ("available_ip_address_count", 0),
    ],
)
async def test_pending_gateway_companion_drift_never_dispatches_again(field, value):
    entry, cloud = NetworkEntry(), NetworkCloud(existing=True)
    entry.row = {"vpc_id": "vpc-one", "subnet_ids": ["subnet-one"]}
    manager = provisioner(cloud)
    network = await manager.ensure(entry)
    cloud.lose = "subnet"
    with pytest.raises(TimeoutError):
        await manager.gateway_network(entry, network, ["cn-beijing-a", "cn-beijing-c"])
    cloud.subnet_rows["subnet-auto"][field] = value
    with pytest.raises(DeploymentError):
        await manager.gateway_network(entry, network, ["cn-beijing-a", "cn-beijing-c"])
    assert len(cloud.calls) == 1


@pytest.mark.asyncio
async def test_pending_gateway_companion_prefix_change_keeps_original_request():
    entry, cloud = NetworkEntry(), NetworkCloud(existing=True)
    entry.row = {"vpc_id": "vpc-one", "subnet_ids": ["subnet-one"]}
    manager = provisioner(cloud)
    network = await manager.ensure(entry)
    cloud.lose = "subnet"
    with pytest.raises(TimeoutError):
        await manager.gateway_network(entry, network, ["cn-beijing-a", "cn-beijing-c"])
    before = copy.deepcopy(entry.row)
    with pytest.raises(DeploymentError, match="CIDR/configuration conflicts"):
        await provisioner(
            cloud, options=NetworkOptions(subnet_prefix=25)
        ).gateway_network(entry, network, ["cn-beijing-a", "cn-beijing-c"])
    assert entry.row == before
    assert len(cloud.calls) == 1


@pytest.mark.asyncio
async def test_gateway_cidr_allocation_keeps_primary_when_subnet_list_lags():
    entry, cloud = NetworkEntry(), NetworkCloud()
    manager = provisioner(cloud)
    network = await manager.ensure(entry)
    # GetSubnet is ready while DescribeSubnets has not caught up yet.
    cloud.hide = True
    await manager.gateway_network(entry, network, ["cn-beijing-a", "cn-beijing-c"])
    assert cloud.calls[-1][1]["cidr_block"] == "172.20.1.0/24"
