"""VPC SDK adapter using the deployment caller's refreshed, verified credentials."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from veadk.integrations.mpa.managed.database import DeploymentError


class NetworkCloudError(DeploymentError):
    def __init__(self, action, code):
        self.code = (
            code
            if isinstance(code, str) and code.replace(".", "").isalnum()
            else "CloudRequestFailed"
        )
        super().__init__(
            f"{action} failed ({self.code}); check deployment IAM permissions and network configuration"
        )


class NetworkCloud:
    def __init__(self, *, region, credentials):
        self.region, self.credentials = region, credentials

    async def call(self, method, request_type, *, ecs=False, **params):
        def run():
            import volcenginesdkcore
            import volcenginesdkecs
            import volcenginesdkvpc

            credential = self.credentials()
            config: Any = volcenginesdkcore.Configuration()
            config.ak, config.sk = (
                credential.access_key_id,
                credential.secret_access_key,
            )
            config.session_token, config.region = credential.session_token, self.region
            config.host = f"{'ecs' if ecs else 'vpc'}.{self.region}.volcengineapi.com"
            sdk = volcenginesdkecs if ecs else volcenginesdkvpc
            client_type = volcenginesdkecs.ECSApi if ecs else volcenginesdkvpc.VPCApi
            request = getattr(sdk, request_type)(**params)
            return getattr(client_type(volcenginesdkcore.ApiClient(config)), method)(
                request,
                _request_timeout=30,
            ).to_dict()

        try:
            return await asyncio.to_thread(run)
        except DeploymentError:
            raise
        except Exception as exc:
            try:
                error = json.loads(getattr(exc, "body", "") or "{}")[
                    "ResponseMetadata"
                ]["Error"]["Code"]
            except (ValueError, KeyError, TypeError):
                error = "CloudRequestFailed"
            raise NetworkCloudError(method, error) from None

    async def zones(self):
        result = await self.call("describe_zones", "DescribeZonesRequest", ecs=True)
        zones = sorted(
            {z["zone_id"] for z in result.get("zones") or [] if z.get("zone_id")}
        )
        if not zones:
            raise DeploymentError(
                "No available zones returned for the deployment region"
            )
        return zones

    async def vpc(self, vpc_id):
        return await self.call(
            "describe_vpc_attributes", "DescribeVpcAttributesRequest", vpc_id=vpc_id
        )

    async def subnet(self, subnet_id):
        return await self.call(
            "describe_subnet_attributes",
            "DescribeSubnetAttributesRequest",
            subnet_id=subnet_id,
        )

    async def _list(self, method, request_type, collection, **params):
        rows = []
        for page in range(1, 1001):
            result = await self.call(
                method, request_type, page_number=page, page_size=100, **params
            )
            items = result.get(collection)
            if not isinstance(items, list):
                raise DeploymentError("Network discovery returned invalid results")
            rows.extend(items)
            if len(items) < 100:
                return rows
        raise DeploymentError("Network discovery pagination exceeded limit")

    async def find_vpcs(self, name):
        rows = await self._list(
            "describe_vpcs", "DescribeVpcsRequest", "vpcs", vpc_name=name
        )
        return [row for row in rows if row.get("vpc_name") == name]

    async def subnets(self, vpc_id):
        return await self._list(
            "describe_subnets", "DescribeSubnetsRequest", "subnets", vpc_id=vpc_id
        )

    async def create_vpc(self, request):
        result = await self.call("create_vpc", "CreateVpcRequest", **request)
        if not result.get("vpc_id"):
            raise DeploymentError(
                "CreateVpc returned no ID; retry discovery before creating another VPC"
            )
        return result["vpc_id"]

    async def create_subnet(self, request):
        result = await self.call("create_subnet", "CreateSubnetRequest", **request)
        if not result.get("subnet_id"):
            raise DeploymentError(
                "CreateSubnet returned no ID; retry discovery before creating another subnet"
            )
        return result["subnet_id"]
