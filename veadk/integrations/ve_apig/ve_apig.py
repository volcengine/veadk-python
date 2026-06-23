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

import time
import json
import volcenginesdkcore
from volcenginesdkapig import APIGApi
from volcenginesdkapig20221112 import APIG20221112Api, UpstreamListForCreateRouteInput

from veadk.utils.volcengine_sign import ve_request


class APIGateway:
    def __init__(self, access_key: str, secret_key: str, region: str = "cn-beijing"):
        self.ak = access_key
        self.sk = secret_key
        self.region = region
        configuration = volcenginesdkcore.Configuration()
        configuration.ak = self.ak
        configuration.sk = self.sk
        configuration.region = region

        self.api_client = volcenginesdkcore.ApiClient(configuration=configuration)
        self.apig_20221112_client = APIG20221112Api(api_client=self.api_client)
        self.apig_client = APIGApi(api_client=self.api_client)

    def list_gateways(self):
        from volcenginesdkapig import ListGatewaysRequest

        request = ListGatewaysRequest()
        thread = self.apig_client.list_gateways(request, async_req=True)
        result = thread.get()
        return result

    def create_serverless_gateway(self, instance_name: str) -> str:  # instance
        from volcenginesdkapig import (
            CreateGatewayRequest,
            ResourceSpecForCreateGatewayInput,
            ListGatewaysRequest,
        )

        request = CreateGatewayRequest(
            name=instance_name,
            region=self.region,
            type="serverless",
            resource_spec=ResourceSpecForCreateGatewayInput(
                replicas=2,
                instance_spec_code="1c2g",
                clb_spec_code="small_1",
                public_network_billing_type="traffic",
                network_type={
                    "EnablePublicNetwork": True,
                    "EnablePrivateNetwork": False,
                },
            ),
        )
        thread = self.apig_client.create_gateway(request, async_req=True)
        result = thread.get()
        gateway_id = result.to_dict()["id"]

        found = False
        while not found:
            request = ListGatewaysRequest()
            thread = self.apig_client.list_gateways(request, async_req=True)
            result = thread.get()
            for item in result.items:
                if (
                    item.to_dict()["id"] == gateway_id
                    and item.to_dict()["status"] == "Running"
                ):
                    found = True
                    break
            if not found:
                time.sleep(5)
        return gateway_id

    def create_gateway_service(self, gateway_id: str, service_name: str) -> str:
        """
        Create a gateway service. (Domain name)
        Args:
            gateway_id (str): The ID of the gateway to which the service belongs.
            service_name (str): The name of the service to be created.
        Returns:
            str: The ID of the created service.
        """
        from volcenginesdkapig import (
            AuthSpecForCreateGatewayServiceInput,
            CreateGatewayServiceRequest,
        )

        request = CreateGatewayServiceRequest(
            gateway_id=gateway_id,
            service_name=service_name,
            protocol=["HTTP", "HTTPS"],
            auth_spec=AuthSpecForCreateGatewayServiceInput(enable=False),
        )
        thread = self.apig_client.create_gateway_service(request, async_req=True)
        result = thread.get()
        return result.to_dict()["id"]

    def create_vefaas_upstream(
        self, function_id: str, gateway_id: str, upstream_name: str
    ):
        from volcenginesdkapig import (
            CreateUpstreamRequest,
            UpstreamSpecForCreateUpstreamInput,
            VeFaasForCreateUpstreamInput,
        )

        request = CreateUpstreamRequest(
            gateway_id=gateway_id,
            name=upstream_name,
            source_type="VeFaas",
            upstream_spec=UpstreamSpecForCreateUpstreamInput(
                ve_faas=VeFaasForCreateUpstreamInput(function_id=function_id)
            ),
        )
        thread = self.apig_client.create_upstream(request, async_req=True)
        result = thread.get()
        return result.to_dict()["id"]

    def create_domain_upstream(
        self,
        domain: str,
        port: int,
        is_https: bool,
        gateway_id: str,
        upstream_name: str,
    ) -> str:
        """
        Create a domain upstream.
        Args:
            domain (str): The domain of the upstream.
            port (int): The port of the upstream.
            is_https (bool): Whether the upstream works on HTTPS.
            gateway_id (str): The ID of the gateway to which the upstream belongs.
            upstream_name (str): The name of the upstream.
        Returns:
            str: The ID of the created upstream.
        """

        request_body = {
            "Name": upstream_name,
            "GatewayId": gateway_id,
            "SourceType": "Domain",
            "UpstreamSpec": {
                "Domain": {"DomainList": [{"Domain": domain, "Port": port}]}
            },
        }
        if is_https:
            request_body["TlsSettings"] = {"TlsMode": "SIMPLE", "Sni": domain}
        else:
            request_body["TlsSettings"] = {"TlsMode": "DISABLE"}

        response = ve_request(
            request_body=request_body,
            action="CreateUpstream",
            ak=self.ak,
            sk=self.sk,
            service="apig",
            version="2021-03-03",
            region=self.region,
            host="open.volcengineapi.com",
        )

        try:
            return response["Result"]["Id"]
        except Exception as _:
            raise ValueError(f"Create domain upstream failed: {response}")

    def check_domain_upstream_exist(
        self, domain: str, port: int, gateway_id: str
    ) -> str | None:
        """
        Check whether the domain upstream exists.
        Args:
            domain (str): The domain of the upstream.
            port (int): The port of the upstream.
            gateway_id (str): The ID of the gateway to which the upstream belongs.
        Returns:
            str | None: The ID of the existed upstream or None if no upstream exists.
        """

        request_body = {
            "GatewayId": gateway_id,
            "UpstreamSpec": {
                "Domain": {"DomainList": [{"Domain": domain, "Port": port}]}
            },
        }

        response = ve_request(
            request_body=request_body,
            action="CheckUpstreamSpecExist",
            ak=self.ak,
            sk=self.sk,
            service="apig",
            version="2021-03-03",
            region=self.region,
            host="open.volcengineapi.com",
        )

        try:
            exist = response["Result"]["Exist"]
            if exist:
                return response["Result"]["Id"]
            else:
                return None
        except Exception as _:
            raise ValueError(f"Check domain upstream spec exist failed: {response}")

    def create_gateway_service_routes(
        self, service_id: str, upstream_id: str, route_name: str, match_rule: dict
    ):
        """
        Create gateway service routes.

        Args:
            service_id (str): The ID of the gateway service, used to specify the target service for which the route is to be created.
            upstream_id (str): The ID of the upstream service, to which the route will point.
            route_name (str): The name of the route to be created.
            match_rule (dict): The route matching rule, containing the following key - value pairs:
                - match_content (str): The path matching content, a string like "/abc", used to specify the path to be matched.
                - match_type (str): The path matching type, with optional values "Exact", "Regex", "Prefix".
                - match_method (list[str]): The list of HTTP request methods, possible values include "GET", "POST", etc.
        Returns:
            str: The ID of the created route.
        """
        from volcenginesdkapig20221112 import (
            CreateRouteRequest,
            MatchRuleForCreateRouteInput,
            PathForCreateRouteInput,
        )

        match_content: str = match_rule["match_content"]
        match_type: str = match_rule["match_type"]
        match_method: list[str] = match_rule["match_method"]

        request = CreateRouteRequest(
            service_id=service_id,
            enable=True,
            match_rule=MatchRuleForCreateRouteInput(
                path=PathForCreateRouteInput(
                    match_content=match_content, match_type=match_type
                ),
                method=match_method,
            ),
            name=route_name,
            priority=1,
            upstream_list=[
                UpstreamListForCreateRouteInput(
                    upstream_id=upstream_id,
                    weight=1,
                )
            ],
        )

        thread = self.apig_20221112_client.create_route(request, async_req=True)
        result = thread.get()
        return result.to_dict()["id"]

    def create_plugin_binding(
        self, scope: str, target: str, plugin_name: str, plugin_config: str
    ) -> str:
        """
        Create a plugin binding.
        Args:
            scope (str): The type of the target.
                Choices are 'GATEWAY', 'SERVICE' or 'ROUTE'.
            target (str): The ID of the gateway, service or route.
            plugin_name (str): The name of the plugin.
            plugin_config (str): The config of the plugin.
        Returns:
            str: The ID of the created service.
        """

        from volcenginesdkapig import CreatePluginBindingRequest

        request = CreatePluginBindingRequest(
            scope=scope,
            target=target,
            plugin_name=plugin_name,
            plugin_config=plugin_config,
            enable=True,
        )
        thread = self.apig_client.create_plugin_binding(request, async_req=True)
        result = thread.get()
        return result.to_dict()["id"]

    def create(
        self,
        function_id: str,
        apig_instance_name: str,
        service_name: str,
        upstream_name: str,
        routes: list[dict],
    ):
        """
        Create an API gateway instance, service, and multiple routes.

        Args:
            function_id (str): The ID of the function to be associated with the routes.
            apig_instance_name (str): The name of the API gateway instance.
            service_name (str): The name of the service to be created.
            upstream_name (str): The name of the upstream service to be created.
            routes (list[dict]): A list of route configurations. Each dictionary in the list contains the following key - value pairs:
                - route_name (str): The name of the route to be created.
                - match_content (str): The path matching content, a string like "/abc", used to specify the path to be matched.
                - match_type (str): The path matching type, with optional values "Exact", "Regex", "Prefix".
                - match_method (list[str]): The list of HTTP request methods, possible values include "GET", "POST", etc.

        Returns:
            dict: A dictionary containing the IDs of the created gateway, service, upstream, and routes.
        """
        gateway_id = self.create_serverless_gateway(apig_instance_name)
        service_id = self.create_gateway_service(gateway_id, service_name)
        upstream_id = self.create_vefaas_upstream(
            function_id, gateway_id, upstream_name
        )

        route_ids = []
        for route in routes:
            route_name = route["route_name"]
            match_rule = {
                "match_content": route["match_content"],
                "match_type": route["match_type"],
                "match_method": route["match_method"],
            }
            route_id = self.create_gateway_service_routes(
                service_id, upstream_id, route_name, match_rule
            )
            route_ids.append(route_id)

        return {
            "gateway_id": gateway_id,
            "service_id": service_id,
            "upstream_id": upstream_id,
            "route_ids": route_ids,
        }

    def create_session_affinity_plugin(self, gateway_id: str) -> str:
        """Create session affinity plugin on gateway. Returns plugin_id."""
        response = ve_request(
            request_body={
                "PluginName": "wasm-session-affinity-pro",
                "PluginConfig": "",
                "GatewayId": gateway_id,
                "Enable": True,
            },
            action="CreatePlugin",
            ak=self.ak,
            sk=self.sk,
            service="apig",
            version="2022-11-12",
            region=self.region,
            host="open.volcengineapi.com",
        )
        return response["Result"]["PluginID"]

    def bind_session_affinity_plugin(self, service_id: str) -> str:
        """Bind session affinity plugin to service. Returns binding_id."""
        plugin_config = json.dumps(
            {
                "Position": "Header",
                "DownstreamSessionKey": "x-session-id-veadk",
                "UpstreamHeaders": [],
                "FailureModeAllow": False,
            }
        )
        return self.create_plugin_binding(
            scope="SERVICE",
            target=service_id,
            plugin_name="wasm-session-affinity-pro",
            plugin_config=plugin_config,
        )

    def delete_plugin_binding(self, binding_id: str) -> None:
        """Delete a plugin binding by id."""
        ve_request(
            request_body={"Id": binding_id},
            action="DeletePluginBinding",
            ak=self.ak,
            sk=self.sk,
            service="apig",
            version="2021-03-03",
            region=self.region,
            host="open.volcengineapi.com",
        )
