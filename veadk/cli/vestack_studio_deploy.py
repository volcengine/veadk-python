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

"""Deploy Studio as a VeStack VeFaaS image function behind APIG."""

from __future__ import annotations

from dataclasses import dataclass
import os
import time

import volcenginesdkvefaas

import veadk.config
from veadk.integrations.ve_apig.ve_apig import APIGateway
from veadk.integrations.ve_faas.ve_faas import VeFaaS


@dataclass(frozen=True)
class VeStackStudioDeployment:
    """Cloud resources created for one Studio image deployment."""

    endpoint: str
    function_id: str
    gateway_id: str
    service_id: str
    upstream_id: str
    route_id: str


_LONG_LIVED_CREDENTIAL_ENV_KEYS = {
    "ACCESS_KEY_ID",
    "SECRET_ACCESS_KEY",
    "VOLCENGINE_ACCESS_KEY",
    "VOLCENGINE_ACCESS_KEY_ID",
    "VOLCENGINE_SECRET_ACCESS_KEY",
    "VOLCENGINE_SECRET_KEY",
}


def _safe_function_environment(environment: dict[str, str]) -> dict[str, str]:
    """Strip deployer credentials before any Function create/update request."""
    return {
        key: value
        for key, value in environment.items()
        if key.upper() not in _LONG_LIVED_CREDENTIAL_ENV_KEYS
    }


def _wait_for_function_release(
    service: VeFaaS,
    function_id: str,
    *,
    attempts: int = 120,
    interval_seconds: float = 5,
) -> None:
    for _ in range(attempts):
        response = service.client.get_release_status(
            volcenginesdkvefaas.GetReleaseStatusRequest(function_id=function_id)
        )
        state = str(getattr(response, "status", "") or "").lower()
        if state == "done" or "succ" in state:
            return
        if "fail" in state or "error" in state:
            raise RuntimeError(f"VeFaaS function release failed: {state}")
        time.sleep(interval_seconds)
    raise TimeoutError("VeFaaS function release did not complete before timeout")


def deploy_vestack_studio_image(
    *,
    access_key: str,
    secret_key: str,
    session_token: str,
    region: str,
    project: str,
    application_name: str,
    image: str,
    role_trn: str,
    public_domain: str,
    gateway_name: str = "",
    gateway_service_name: str = "",
    gateway_upstream_name: str = "",
    apig_cluster_id: str = "",
    apig_namespace: str = "",
    apig_cluster_name: str = "aio",
    environment: dict[str, str] | None = None,
) -> VeStackStudioDeployment:
    """Create and release a VeFaaS Function, then expose it through APIG.

    VeStack does not provide the public-cloud VeFaaS Application/BFF API.  This
    function performs the Application's essential orchestration explicitly.
    Long-lived deployer credentials are used only to sign control-plane calls;
    they are never copied into the Function environment.
    """
    if not image.strip():
        raise ValueError("A VeStack Studio image is required")
    if not public_domain.strip():
        raise ValueError("A dedicated Studio public domain is required")

    function_name = f"{application_name}-fn"
    gateway_name = gateway_name or f"{application_name}-gateway"
    gateway_service_name = gateway_service_name or f"{application_name}-service"
    gateway_upstream_name = gateway_upstream_name or f"{application_name}-upstream"

    requested_environment = _safe_function_environment(environment or {})
    veadk.config.veadk_environments.clear()
    veadk.config.veadk_environments.update(requested_environment)

    service = VeFaaS(
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        region=region,
        project_name=project,
        provider="volcengine",
    )
    # IAM_ROLE is intentionally read by the create request rather than included
    # in ``veadk_environments`` so no long-lived credential reaches the pod.
    previous_role = os.environ.get("IAM_ROLE")
    os.environ["IAM_ROLE"] = role_trn
    try:
        functions = list(
            getattr(
                service.client.list_functions(
                    volcenginesdkvefaas.ListFunctionsRequest(
                        page_number=1, page_size=100
                    )
                ),
                "items",
                None,
            )
            or []
        )
        existing_function = next(
            (item for item in functions if getattr(item, "name", "") == function_name),
            None,
        )
        if existing_function is None:
            _, function_id = service._create_image_function(function_name, image)
        else:
            function_id = str(getattr(existing_function, "id"))
            current_function = service.client.get_function(
                volcenginesdkvefaas.GetFunctionRequest(id=function_id)
            )
            deployed_environment = _safe_function_environment(
                {
                    str(item.key): str(item.value)
                    for item in (getattr(current_function, "envs", None) or [])
                }
            )
            deployed_environment.update(requested_environment)
            veadk.config.veadk_environments.clear()
            veadk.config.veadk_environments.update(deployed_environment)
            service.client.update_function(
                volcenginesdkvefaas.UpdateFunctionRequest(
                    id=function_id,
                    command="bash ./run.sh",
                    source_type="image",
                    source=image,
                    envs=[
                        volcenginesdkvefaas.EnvForUpdateFunctionInput(
                            key=key, value=value
                        )
                        for key, value in sorted(deployed_environment.items())
                    ],
                    memory_mb=4096,
                    role=role_trn,
                    project_name=project,
                )
            )
    finally:
        if previous_role is None:
            os.environ.pop("IAM_ROLE", None)
        else:
            os.environ["IAM_ROLE"] = previous_role

    service.client.release(
        volcenginesdkvefaas.ReleaseRequest(
            function_id=function_id,
            revision_number=0,
        )
    )
    _wait_for_function_release(service, function_id)

    apig = APIGateway(
        access_key,
        secret_key,
        region,
        session_token=session_token,
        provider="volcengine",
    )
    gateways = list(getattr(apig.list_gateways(), "items", None) or [])
    gateway = next(
        (item for item in gateways if getattr(item, "name", "") == gateway_name),
        None,
    )
    gateway_id = (
        str(getattr(gateway, "id", ""))
        if gateway is not None
        else apig.create_serverless_gateway(
            gateway_name,
            vestack_cluster_id=apig_cluster_id,
            vestack_namespace=apig_namespace,
            vestack_cluster_name=apig_cluster_name,
        )
    )
    gateway_service = apig.find_gateway_service(gateway_id, gateway_service_name)
    service_id = (
        str(getattr(gateway_service, "id"))
        if gateway_service is not None
        else apig.create_gateway_service(
            gateway_id,
            gateway_service_name,
            custom_domain=public_domain,
            vestack=bool(apig_cluster_id),
        )
    )
    upstream = apig.find_upstream(gateway_id, gateway_upstream_name)
    upstream_id = (
        str(getattr(upstream, "id"))
        if upstream is not None
        else apig.create_vefaas_upstream(
            function_id,
            gateway_id,
            gateway_upstream_name,
        )
    )
    route_name = f"{application_name}-root"
    route = apig.find_route(service_id, route_name)
    route_id = (
        str(getattr(route, "id"))
        if route is not None
        else apig.create_gateway_service_routes(
            service_id,
            upstream_id,
            route_name,
            {
                "match_content": "/",
                "match_type": "Prefix",
                "match_method": [
                    "GET",
                    "POST",
                    "PUT",
                    "DELETE",
                    "PATCH",
                    "HEAD",
                    "OPTIONS",
                ],
            },
        )
    )
    if apig_cluster_id:
        _, public_port = apig.get_gateway_external_http_address(gateway_id)
        endpoint = f"http://{public_domain.strip().rstrip('/')}:{public_port}"
    else:
        endpoint = f"http://{public_domain.strip().rstrip('/')}"
    service.update_function_envs_and_release(
        function_id,
        {"OAUTH2_REDIRECT_URI": f"{endpoint}/oauth2/callback"},
    )
    return VeStackStudioDeployment(
        endpoint=endpoint,
        function_id=function_id,
        gateway_id=gateway_id,
        service_id=service_id,
        upstream_id=upstream_id,
        route_id=route_id,
    )
