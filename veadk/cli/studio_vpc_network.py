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

"""Discover the VPC address space attached to a cloud-hosted Studio."""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping
from typing import Any

import volcenginesdkcore
import volcenginesdkvefaas
import volcenginesdkvpc

from veadk.utils.cloud_provider import CloudProvider, vefaas_openapi_host

IpNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


class StudioVpcDiscoveryError(RuntimeError):
    """Raised when a VeFaaS Studio's attached VPC cannot be determined."""


def is_vefaas_runtime(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether the current process is running as a VeFaaS function."""
    values = os.environ if environ is None else environ
    return bool(
        str(values.get("VEADK_STUDIO_FUNCTION_ID") or "").strip()
        or str(values.get("_FAAS_FUNC_ID") or "").strip()
    )


def studio_function_id(environ: Mapping[str, str] | None = None) -> str:
    values = os.environ if environ is None else environ
    return str(
        values.get("VEADK_STUDIO_FUNCTION_ID") or values.get("_FAAS_FUNC_ID") or ""
    ).strip()


def _configuration(
    *,
    access_key: str,
    secret_key: str,
    session_token: str | None,
    region: str,
    host: str | None = None,
) -> volcenginesdkcore.Configuration:
    configuration = volcenginesdkcore.Configuration()
    configuration.ak = access_key
    configuration.sk = secret_key
    configuration.session_token = session_token or ""
    configuration.region = region
    if host:
        configuration.host = f"https://{host}"
    configuration.client_side_validation = True
    return configuration


def _vefaas_client(
    *,
    provider: CloudProvider,
    region: str,
    access_key: str,
    secret_key: str,
    session_token: str | None,
) -> Any:
    configuration = _configuration(
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        region=region,
        host=(
            vefaas_openapi_host(region, provider) if provider == "byteplus" else None
        ),
    )
    return volcenginesdkvefaas.VEFAASApi(volcenginesdkcore.ApiClient(configuration))


def _vpc_client(
    *,
    provider: CloudProvider,
    region: str,
    access_key: str,
    secret_key: str,
    session_token: str | None,
) -> Any:
    configuration = _configuration(
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        region=region,
        host=(f"vpc.{region}.byteplusapi.com" if provider == "byteplus" else None),
    )
    return volcenginesdkvpc.VPCApi(volcenginesdkcore.ApiClient(configuration))


def _network(value: object) -> IpNetwork | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return ipaddress.ip_network(text, strict=False)
    except ValueError as exc:
        raise StudioVpcDiscoveryError("VeFaaS returned an invalid VPC CIDR.") from exc


def _add_network(target: set[IpNetwork], value: object) -> None:
    network = _network(value)
    if network is not None:
        target.add(network)


def discover_studio_vpc_networks(
    *,
    provider: CloudProvider,
    region: str,
    access_key: str,
    secret_key: str,
    session_token: str | None = None,
    function_id: str,
    vefaas_client: Any | None = None,
    vpc_client: Any | None = None,
) -> tuple[IpNetwork, ...]:
    """Return the VPC and subnet CIDRs attached to ``function_id``.

    PrivateLink endpoints in the consumer VPC resolve to endpoint ENI addresses
    from these ranges, so no per-MCP endpoint registration is required.
    """
    if not function_id.strip():
        raise StudioVpcDiscoveryError("The current VeFaaS function ID is unavailable.")

    try:
        function_client = vefaas_client or _vefaas_client(
            provider=provider,
            region=region,
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
        )
        function = function_client.get_function(
            volcenginesdkvefaas.GetFunctionRequest(id=function_id)
        )
        vpc_config = getattr(function, "vpc_config", None)
        vpc_id = str(getattr(vpc_config, "vpc_id", "") or "").strip()
        if not vpc_config or not getattr(vpc_config, "enable_vpc", False) or not vpc_id:
            return ()

        network_client = vpc_client or _vpc_client(
            provider=provider,
            region=region,
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
        )
        vpc = network_client.describe_vpc_attributes(
            volcenginesdkvpc.DescribeVpcAttributesRequest(vpc_id=vpc_id)
        )
        networks: set[IpNetwork] = set()
        _add_network(networks, getattr(vpc, "cidr_block", ""))
        _add_network(networks, getattr(vpc, "ipv6_cidr_block", ""))
        for attr in ("secondary_cidr_blocks", "user_cidr_blocks"):
            for cidr in getattr(vpc, attr, None) or ():
                _add_network(networks, cidr)
        for value in getattr(vpc, "ipv6_cidr_blocks", None) or ():
            _add_network(networks, getattr(value, "ipv6_cidr_block", value))

        for subnet_id in getattr(vpc_config, "subnet_ids", None) or ():
            subnet = network_client.describe_subnet_attributes(
                volcenginesdkvpc.DescribeSubnetAttributesRequest(
                    subnet_id=str(subnet_id)
                )
            )
            subnet_vpc_id = str(getattr(subnet, "vpc_id", "") or "").strip()
            if subnet_vpc_id and subnet_vpc_id != vpc_id:
                raise StudioVpcDiscoveryError(
                    "VeFaaS returned a subnet outside the attached VPC."
                )
            _add_network(networks, getattr(subnet, "cidr_block", ""))
            _add_network(networks, getattr(subnet, "ipv6_cidr_block", ""))

        return tuple(
            sorted(
                networks,
                key=lambda item: (
                    item.version,
                    int(item.network_address),
                    item.prefixlen,
                ),
            )
        )
    except StudioVpcDiscoveryError:
        raise
    except Exception as exc:
        raise StudioVpcDiscoveryError(
            "Failed to query the current VeFaaS VPC configuration."
        ) from exc
