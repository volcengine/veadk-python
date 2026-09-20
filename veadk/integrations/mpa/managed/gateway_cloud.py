"""Deployment-only APIG operations using the verified Runtime credential source."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any


class APIGClientError(RuntimeError):
    def __init__(self, message: str, *, code: str = ""):
        super().__init__(message)
        self.code = code


class GatewayCloud:
    def __init__(self, runtime_cloud):
        self.runtime = runtime_cloud

    async def account_id(self):
        return await self.runtime.account_id()

    async def call(self, action, body):
        def run():
            from volcenginesdkcore import ApiClient, Configuration
            from volcenginesdkcore.universal import UniversalApi, UniversalInfo

            credential = self.runtime._credentials()
            config: Any = Configuration()
            config.ak, config.sk = (
                credential.access_key_id,
                credential.secret_access_key,
            )
            config.session_token = credential.session_token
            config.region = self.runtime.region
            config.host = f"apig.{config.region}.volcengineapi.com"
            client = ApiClient(config)
            info = UniversalInfo(
                method="POST",
                service="apig",
                version="2021-03-03",
                action=action,
                content_type="application/json",
            )
            try:
                response = UniversalApi(client).do_call(info, body, _request_timeout=30)
                if isinstance(response, (str, bytes)):
                    response = json.loads(response)
                if not isinstance(response, dict) or not (
                    isinstance(response.get("Result"), dict)
                    or response.get("Error")
                    or (response.get("ResponseMetadata") or {}).get("Error")
                ):
                    response = json.loads(
                        getattr(getattr(client, "last_response", None), "data", b"{}")
                    )
                error = (response.get("ResponseMetadata") or {}).get(
                    "Error"
                ) or response.get("Error")
                if error:
                    raise APIGClientError(
                        "APIG request rejected",
                        code=error.get("Code", "CloudRequestFailed"),
                    )
                result = response.get("Result")
                if not isinstance(result, dict):
                    raise APIGClientError("Invalid APIG response")
                return result
            except APIGClientError:
                raise
            except Exception as exc:
                try:
                    code = json.loads(getattr(exc, "body", "{}"))["ResponseMetadata"][
                        "Error"
                    ]["Code"]
                except (ValueError, KeyError, TypeError):
                    code = "CloudRequestFailed"
                if not isinstance(code, str) or not code.replace(".", "").isalnum():
                    code = "CloudRequestFailed"
                raise APIGClientError(f"{action} failed ({code})", code=code) from None

        return await asyncio.to_thread(run)

    async def find_gateways(self, name):
        matches = []
        for page in range(1, 1001):
            result = await self.call(
                "ListGateways",
                {"PageNumber": page, "PageSize": 100, "Filter": {"Name": name}},
            )
            items = result.get("Items")
            if not isinstance(items, list):
                raise APIGClientError("Invalid gateway list")
            matches.extend(item for item in items if item.get("Name") == name)
            if len(items) < 100:
                return matches
        raise APIGClientError("Gateway pagination exceeded limit")

    async def create_gateway(self, name, vpc_id, subnet_ids):
        result = await self.call(
            "CreateGateway",
            {
                "Name": name,
                "Region": self.runtime.region,
                "Type": "serverless",
                "NetworkSpec": {"VpcId": vpc_id, "SubnetIds": subnet_ids},
                "ResourceSpec": {
                    "Replicas": 2,
                    "InstanceSpecCode": "1c2g",
                    "ClbSpecCode": "small_1",
                    "PublicNetworkBillingType": "traffic",
                    "NetworkType": {
                        "EnablePublicNetwork": True,
                        "EnablePrivateNetwork": True,
                    },
                },
            },
        )
        if not result.get("Id"):
            raise APIGClientError("Gateway creation outcome unknown; retry discovery")
        return result["Id"]

    async def get_gateway(self, gateway_id):
        result = await self.call("GetGateway", {"Id": gateway_id})
        gateway = result.get("Gateway")
        if not isinstance(gateway, dict) or gateway.get("Id") != gateway_id:
            raise APIGClientError("Invalid gateway metadata")
        return gateway

    async def create_im_gateway_service(self, *, gateway_id):
        await self.call("CreateIMChannelGateway", {"GatewayId": gateway_id})

    async def get_im_gateway_service_status(self, *, gateway_id):
        result = await self.call("GetIMChannelGatewayStatus", {"GatewayId": gateway_id})
        return SimpleNamespace(
            status=result.get("Status", ""),
            im_gateway_endpoint=result.get("IMGatewayPrivateEndpoint", ""),
            im_gateway_service_id=result.get("RuntimeServiceId", ""),
        )

    async def wait_im_gateway_service_ready(self, *, gateway_id):
        for _ in range(60):
            result = await self.get_im_gateway_service_status(gateway_id=gateway_id)
            if (
                result.status == "RUNNING"
                and result.im_gateway_endpoint
                and result.im_gateway_service_id
            ):
                return result
            if result.status == "FAILED":
                raise APIGClientError(
                    "IM Gateway failed; inspect the registered service"
                )
            await asyncio.sleep(5)
        raise APIGClientError("IM Gateway readiness timed out; retry the same agent")
