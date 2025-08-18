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

import volcenginesdkcore
from volcenginesdkapig import (
    APIGApi,
    ListGatewaysRequest,
    UpstreamSpecForCreateUpstreamInput,
    VeFaasForCreateUpstreamInput,
)
from volcenginesdkapig20221112 import APIG20221112Api, UpstreamListForCreateRouteInput


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
        request = ListGatewaysRequest()
        thread = self.apig_client.list_gateways(request, async_req=True)
        result = thread.get()
        return result

    def create_serverless_gateway(self, instance_name: str) -> str:  # instance
        from volcenginesdkapig import (
            CreateGatewayRequest,
            ResourceSpecForCreateGatewayInput,
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

    def create_upstream(self, function_id: str, gateway_id: str, upstream_name: str):
        from volcenginesdkapig import CreateUpstreamRequest

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
        upstream_id = self.create_upstream(function_id, gateway_id, upstream_name)

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
