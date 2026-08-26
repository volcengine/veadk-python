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

from __future__ import annotations

from types import SimpleNamespace

import pytest

from veadk.cli.studio_vpc_network import (
    StudioVpcDiscoveryError,
    discover_studio_vpc_networks,
    is_vefaas_runtime,
    studio_function_id,
)


class _VeFaaSClient:
    def __init__(self, vpc_config: object) -> None:
        self.vpc_config = vpc_config
        self.function_ids: list[str] = []

    def get_function(self, request: object) -> object:
        self.function_ids.append(str(getattr(request, "id")))
        return SimpleNamespace(vpc_config=self.vpc_config)


class _VpcClient:
    def __init__(self) -> None:
        self.vpc_ids: list[str] = []
        self.subnet_ids: list[str] = []

    def describe_vpc_attributes(self, request: object) -> object:
        self.vpc_ids.append(str(getattr(request, "vpc_id")))
        return SimpleNamespace(
            cidr_block="10.20.0.0/16",
            secondary_cidr_blocks=["10.30.0.0/16"],
            user_cidr_blocks=["100.96.0.0/16"],
            ipv6_cidr_block="fd00:20::/56",
            ipv6_cidr_blocks=[],
        )

    def describe_subnet_attributes(self, request: object) -> object:
        subnet_id = str(getattr(request, "subnet_id"))
        self.subnet_ids.append(subnet_id)
        return SimpleNamespace(
            vpc_id="vpc-test",
            cidr_block="10.20.8.0/24",
            ipv6_cidr_block="fd00:20:0:8::/64",
        )


def test_vefaas_runtime_detection_and_function_id_fallback() -> None:
    assert not is_vefaas_runtime({})
    assert is_vefaas_runtime({"_FAAS_FUNC_ID": "function-runtime"})
    assert studio_function_id({"_FAAS_FUNC_ID": "function-runtime"}) == (
        "function-runtime"
    )
    assert (
        studio_function_id(
            {
                "_FAAS_FUNC_ID": "function-runtime",
                "VEADK_STUDIO_FUNCTION_ID": "function-studio",
            }
        )
        == "function-studio"
    )


def test_discovers_vpc_primary_secondary_user_and_subnet_cidrs() -> None:
    vefaas = _VeFaaSClient(
        SimpleNamespace(
            enable_vpc=True,
            vpc_id="vpc-test",
            subnet_ids=["subnet-test"],
        )
    )
    vpc = _VpcClient()

    networks = discover_studio_vpc_networks(
        provider="volcengine",
        region="cn-beijing",
        access_key="ak",
        secret_key="sk",
        function_id="function-test",
        vefaas_client=vefaas,
        vpc_client=vpc,
    )

    assert {str(network) for network in networks} == {
        "10.20.0.0/16",
        "10.20.8.0/24",
        "10.30.0.0/16",
        "100.96.0.0/16",
        "fd00:20::/56",
        "fd00:20:0:8::/64",
    }
    assert vefaas.function_ids == ["function-test"]
    assert vpc.vpc_ids == ["vpc-test"]
    assert vpc.subnet_ids == ["subnet-test"]


def test_returns_no_private_ranges_when_function_has_no_vpc() -> None:
    networks = discover_studio_vpc_networks(
        provider="volcengine",
        region="cn-beijing",
        access_key="ak",
        secret_key="sk",
        function_id="function-test",
        vefaas_client=_VeFaaSClient(None),
        vpc_client=_VpcClient(),
    )

    assert networks == ()


def test_rejects_subnet_outside_function_vpc() -> None:
    vefaas = _VeFaaSClient(
        SimpleNamespace(
            enable_vpc=True,
            vpc_id="vpc-test",
            subnet_ids=["subnet-test"],
        )
    )
    vpc = _VpcClient()

    def mismatched_subnet(request: object) -> object:
        return SimpleNamespace(
            vpc_id="vpc-other",
            cidr_block="10.99.0.0/24",
            ipv6_cidr_block="",
        )

    vpc.describe_subnet_attributes = mismatched_subnet  # type: ignore[method-assign]
    with pytest.raises(StudioVpcDiscoveryError, match="outside the attached VPC"):
        discover_studio_vpc_networks(
            provider="volcengine",
            region="cn-beijing",
            access_key="ak",
            secret_key="sk",
            function_id="function-test",
            vefaas_client=vefaas,
            vpc_client=vpc,
        )
