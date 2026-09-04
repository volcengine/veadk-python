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

import json
import os
import time

import volcenginesdkcore
from volcenginesdkapig import APIGApi
from volcenginesdkapig20221112 import APIG20221112Api, UpstreamListForCreateRouteInput

from veadk.utils.cloud_provider import (
    DEFAULT_CLOUD_PROVIDER,
    CloudProvider,
    apig_openapi_host,
    configure_openapi_tls,
)
from veadk.utils.volcengine_sign import ve_request


class APIGateway:
    def __init__(
        self,
        access_key: str,
        secret_key: str,
        region: str = "",
        session_token: str = "",
        provider: CloudProvider = DEFAULT_CLOUD_PROVIDER,
    ):
        self.ak = access_key
        self.sk = secret_key
        self.session_token = session_token
        self.provider = provider
        if not region and provider != "byteplus":
            region = os.getenv("REGION") or "cn-beijing"
        elif not region:
            region = "cn-beijing"
        self.region = region
        self.openapi_host = apig_openapi_host(region, provider)
        configuration = volcenginesdkcore.Configuration()
        configuration.ak = self.ak
        configuration.sk = self.sk
        configuration.session_token = self.session_token
        configuration.region = region
        scheme = os.getenv("APIG_OPENAPI_SCHEME", "https").strip() or "https"
        configuration.host = f"{scheme}://{self.openapi_host}"
        configure_openapi_tls(configuration)

        self.api_client = volcenginesdkcore.ApiClient(configuration=configuration)
        self.apig_20221112_client = APIG20221112Api(api_client=self.api_client)
        self.apig_client = APIGApi(api_client=self.api_client)

    def list_gateways(self):
        from volcenginesdkapig import ListGatewaysRequest

        request = ListGatewaysRequest()
        thread = self.apig_client.list_gateways(request, async_req=True)
        result = thread.get()
        return result

    def find_serverless_gateway(self):
        """Return a serverless APIG gateway to reuse, or None.

        VeFaaS applications can only attach to a *serverless* gateway. Lists a
        full page (the default page size misses gateways past the first ~10) and
        prefers a Running one; falls back to any serverless gateway so callers
        can surface a clearer error than "not found".
        """
        from volcenginesdkapig import ListGatewaysRequest

        request = ListGatewaysRequest(page_number=1, page_size=100)
        result = self.apig_client.list_gateways(request, async_req=True).get()
        items = getattr(result, "items", []) or []
        serverless = [g for g in items if getattr(g, "type", None) == "serverless"]

        def _running(g) -> bool:
            return (
                getattr(g, "message", None) or getattr(g, "status", None)
            ) == "Running"

        running = [g for g in serverless if _running(g)]
        if running:
            return running[0]
        return serverless[0] if serverless else None

    def create_serverless_gateway(
        self,
        instance_name: str,
        *,
        vestack_cluster_id: str = "",
        vestack_namespace: str = "",
        vestack_cluster_name: str = "aio",
    ) -> str:  # instance
        from volcenginesdkapig import (
            CreateGatewayRequest,
            ResourceSpecForCreateGatewayInput,
            ListGatewaysRequest,
        )

        if vestack_cluster_id:
            if not vestack_namespace:
                raise ValueError("VeStack APIG namespace is required")
            # VeStack APIG v2.5 uses the same OpenAPI action/version but a
            # cluster-native request shape that is not represented by the
            # public-cloud Python SDK models. Extend the generated model so the
            # SDK still performs signing, retries, and endpoint configuration.
            request = CreateGatewayRequest(
                name=instance_name,
                region=self.region,
                type="serverless",
                resource_spec={
                    "Replicas": 2,
                    "CpuRequest": "100m",
                    "CpuLimit": "1000m",
                    "MemoryRequest": "128Mi",
                    "MemoryLimit": "1Gi",
                },
            )
            request.swagger_types = dict(request.swagger_types)
            request.attribute_map = dict(request.attribute_map)
            request.swagger_types["resource_spec"] = "object"
            request.swagger_types["cluster_spec"] = "object"
            request.attribute_map["cluster_spec"] = "ClusterSpec"
            request.cluster_spec = {
                "ClusterId": vestack_cluster_id,
                "Namespace": vestack_namespace,
                "ClusterName": vestack_cluster_name,
            }
        else:
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

    def get_gateway_external_http_address(self, gateway_id: str) -> tuple[str, int]:
        """Return the VeStack gateway's external IP and allocated HTTP port."""
        from volcenginesdkapig import GetGatewayRequest

        captured: dict[str, object] = {}
        rest_client = self.apig_client.api_client.rest_client
        original_request = rest_client.request

        def capture_response(*args, **kwargs):
            response = original_request(*args, **kwargs)
            payload = response.data
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8")
            captured.update(json.loads(payload))
            return response

        rest_client.request = capture_response
        try:
            self.apig_client.get_gateway(GetGatewayRequest(id=gateway_id))
        finally:
            rest_client.request = original_request

        gateway = captured.get("Result", {}).get("Gateway", {})
        external = gateway.get("GatewayExternalAddress", {})
        ips = external.get("IPs", [])
        http_item = next(
            (
                item
                for item in external.get("Items", [])
                if str(item.get("Protocol", "")).upper() == "HTTP"
            ),
            None,
        )
        if not ips or not http_item or not http_item.get("Port"):
            raise RuntimeError("VeStack APIG did not return an external HTTP address")
        return str(ips[0]), int(http_item["Port"])

    def create_gateway_service(
        self,
        gateway_id: str,
        service_name: str,
        custom_domain: str = "",
        *,
        vestack: bool = False,
    ) -> str:
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
            CustomDomainForCreateGatewayServiceInput,
            CreateGatewayServiceRequest,
        )

        request = CreateGatewayServiceRequest(
            gateway_id=gateway_id,
            service_name=service_name,
            protocol=["HTTP", "HTTPS"],
            auth_spec=AuthSpecForCreateGatewayServiceInput(enable=False),
            custom_domains=(
                [
                    CustomDomainForCreateGatewayServiceInput(
                        domain=custom_domain,
                        protocol=["HTTP"],
                        ssl_redirect=False,
                    )
                ]
                if custom_domain and not vestack
                else None
            ),
        )
        if vestack:
            if not custom_domain:
                raise ValueError("VeStack APIG service requires a domain")
            request.swagger_types = dict(request.swagger_types)
            request.attribute_map = dict(request.attribute_map)
            request.swagger_types["service_domain_spec"] = "object"
            request.attribute_map["service_domain_spec"] = "ServiceDomainSpec"
            request.service_domain_spec = [
                {"Domain": custom_domain, "Protocol": ["HTTP"]}
            ]
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

    def find_gateway_service(self, gateway_id: str, name: str):
        from volcenginesdkapig import ListGatewayServicesRequest

        result = self.apig_client.list_gateway_services(
            ListGatewayServicesRequest(
                gateway_id=gateway_id, page_number=1, page_size=100
            )
        )
        return next(
            (
                item
                for item in (getattr(result, "items", None) or [])
                if getattr(item, "name", "") == name
            ),
            None,
        )

    def find_upstream(self, gateway_id: str, name: str):
        from volcenginesdkapig import ListUpstreamsRequest

        result = self.apig_client.list_upstreams(
            ListUpstreamsRequest(gateway_id=gateway_id, page_number=1, page_size=100)
        )
        return next(
            (
                item
                for item in (getattr(result, "items", None) or [])
                if getattr(item, "name", "") == name
            ),
            None,
        )

    def find_route(self, service_id: str, name: str):
        from volcenginesdkapig20221112 import ListRoutesRequest

        result = self.apig_20221112_client.list_routes(
            ListRoutesRequest(service_id=service_id, page_number=1, page_size=100)
        )
        return next(
            (
                item
                for item in (getattr(result, "items", None) or [])
                if getattr(item, "name", "") == name
            ),
            None,
        )

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
            host=self.openapi_host,
            session_token=self.session_token,
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
            host=self.openapi_host,
            session_token=self.session_token,
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
