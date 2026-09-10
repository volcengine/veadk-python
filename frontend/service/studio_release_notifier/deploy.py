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

"""Provision the release notifier with AK/SK, a scoped IAM role and HTTPS."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any
from collections.abc import Callable

from veadk.cloud.cloud_agent_engine import CloudAgentEngine
from veadk.utils.cloud_provider import CloudProvider, iam_openapi_host

_FUNCTION_NAME = "veadk-studio-release-notifier"
_GATEWAY_NAME = "test-api-gateway"
_GATEWAY_SERVICE_NAME = _FUNCTION_NAME
_GATEWAY_UPSTREAM_NAME = _FUNCTION_NAME
_GATEWAY_ROUTE_NAME = _FUNCTION_NAME
_GATEWAY_TIMEOUT_MILLISECONDS = 180000
_RESOURCE_NOTE = "勿删：Studio 发版飞书群通知 Webhook"
_ROLE_NAME = "VeADKStudioReleaseNotifierRole"
_POLICY_NAME = "VeADKStudioReleaseNotifierPolicy"
_TRUST_POLICY = {
    "Statement": [
        {
            "Effect": "Allow",
            "Action": ["sts:AssumeRole"],
            "Principal": {"Service": ["vefaas"]},
        }
    ]
}
_TOS_POLICY = {
    "Statement": [
        {
            "Effect": "Allow",
            "Action": ["tos:GetObject", "tos:PutObject"],
            "Resource": ["trn:tos:::veadk-studio/veadk/studio/release-notifications/*"],
        }
    ]
}


def _result(response: dict[str, Any]) -> dict[str, Any]:
    metadata = response.get("ResponseMetadata", {}) or {}
    if metadata.get("Error"):
        error = metadata["Error"]
        raise RuntimeError(error.get("Message") or str(error))
    return response.get("Result", {}) or {}


def _role_trn(result: dict[str, Any]) -> str:
    role = result.get("Role") or result
    return str(role.get("Trn") or role.get("trn") or "")


def _ensure_runtime_role(
    access_key: str,
    secret_key: str,
    *,
    provider: CloudProvider,
    session_token: str = "",
) -> str:
    """Create or refresh the minimal VeFaaS role used for TOS publishing."""
    from volcengine.iam.IamService import IamService

    iam = IamService()
    iam.set_ak(access_key)
    iam.set_sk(secret_key)
    iam.set_host(iam_openapi_host(provider))
    if provider == "byteplus":
        iam.set_scheme("https")
    if session_token:
        iam.set_session_token(session_token)
    policy_document = json.dumps(_TOS_POLICY)
    try:
        _result(
            iam.update_policy(
                {
                    "PolicyName": _POLICY_NAME,
                    "NewPolicyDocument": policy_document,
                }
            )
        )
    except Exception as update_error:  # noqa: BLE001 - SDK has no common error type
        try:
            _result(
                iam.create_policy(
                    {
                        "PolicyName": _POLICY_NAME,
                        "PolicyDocument": policy_document,
                        "Description": _RESOURCE_NOTE,
                    }
                )
            )
        except Exception as create_error:  # noqa: BLE001 - preserve both SDK errors
            raise RuntimeError(
                f"Could not create or update IAM policy: {create_error}"
            ) from update_error

    try:
        role_result = _result(iam.get_role({"RoleName": _ROLE_NAME}))
    except Exception:  # noqa: BLE001 - absent roles are reported as SDK exceptions
        role_result = _result(
            iam.create_role(
                {
                    "RoleName": _ROLE_NAME,
                    "TrustPolicyDocument": json.dumps(_TRUST_POLICY),
                    "Description": _RESOURCE_NOTE,
                }
            )
        )
    trn = _role_trn(role_result)
    if not trn:
        trn = _role_trn(_result(iam.get_role({"RoleName": _ROLE_NAME})))
    if not trn:
        raise RuntimeError("Could not resolve release server IAM role TRN.")

    attached = _result(iam.list_attached_role_policies({"RoleName": _ROLE_NAME})).get(
        "AttachedPolicyMetadata", []
    )
    if not any(item.get("PolicyName") == _POLICY_NAME for item in attached):
        _result(
            iam.attach_role_policy(
                {
                    "RoleName": _ROLE_NAME,
                    "PolicyName": _POLICY_NAME,
                    "PolicyType": "Custom",
                }
            )
        )
    return trn


def _find_named(items: list[Any], name: str) -> Any | None:
    matches = [item for item in items if getattr(item, "name", None) == name]
    if len(matches) > 1:
        raise RuntimeError(f"Multiple cloud resources are named {name}.")
    return matches[0] if matches else None


def _find_function(service: Any) -> Any | None:
    from volcenginesdkvefaas import ListFunctionsRequest

    page_number = 1
    page_size = 100
    functions: list[Any] = []
    while True:
        response = service.client.list_functions(
            ListFunctionsRequest(page_number=page_number, page_size=page_size)
        )
        functions.extend(list(getattr(response, "items", []) or []))
        total = int(getattr(response, "total", 0) or 0)
        if page_number * page_size >= total:
            break
        page_number += 1
    return _find_named(functions, _FUNCTION_NAME)


def _retry_code_upload(operation: Callable[[], None]) -> None:
    """Retry transient presigned-URL failures without masking other errors."""
    for attempt in range(1, 4):
        try:
            operation()
            return
        except ValueError as error:
            if "Function code upload request failed" not in str(error) or attempt == 3:
                raise
            time.sleep(2**attempt)


def _release_function(service: Any, function_id: str) -> None:
    from volcenginesdkvefaas import GetReleaseStatusRequest, ReleaseRequest

    service.client.release(ReleaseRequest(function_id=function_id, revision_number=0))
    for _ in range(120):
        response = service.client.get_release_status(
            GetReleaseStatusRequest(function_id=function_id)
        )
        state = str(getattr(response, "status", "") or "").lower()
        if "succ" in state or state == "done":
            return
        if "fail" in state or "error" in state:
            raise RuntimeError(f"Function release failed: {state}")
        time.sleep(5)
    raise RuntimeError("Function release did not finish in 10 minutes.")


def _https_endpoint(gateway_service: Any) -> str:
    for domain in getattr(gateway_service, "domains", []) or []:
        value = (
            domain.get("domain", "")
            if isinstance(domain, dict)
            else getattr(domain, "domain", "")
        )
        if str(value).startswith("https://"):
            return str(value).rstrip("/")
    return ""


def _find_reusable_serverless_gateway(gateways: list[Any]) -> Any | None:
    """Return an existing running serverless gateway when quota blocks a new one."""
    return next(
        (
            gateway
            for gateway in gateways
            if getattr(gateway, "type", None) == "serverless"
            and (getattr(gateway, "status", None) or getattr(gateway, "message", None))
            == "Running"
        ),
        None,
    )


def _create_serverless_gateway(apig: Any) -> str:
    from volcenginesdkapig import (
        CreateGatewayRequest,
        ListGatewaysRequest,
        ResourceSpecForCreateGatewayInput,
    )

    response = apig.apig_client.create_gateway(
        CreateGatewayRequest(
            comments=_RESOURCE_NOTE,
            name=_GATEWAY_NAME,
            region=apig.region,
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
        ),
        async_req=True,
    ).get()
    gateway_id = str(response.id)
    for _ in range(120):
        gateways = apig.apig_client.list_gateways(
            ListGatewaysRequest(page_number=1, page_size=100),
            async_req=True,
        ).get()
        gateway = _find_named(
            list(getattr(gateways, "items", []) or []),
            _GATEWAY_NAME,
        )
        if gateway is not None:
            state = getattr(gateway, "status", None) or getattr(
                gateway, "message", None
            )
            if state == "Running":
                return gateway_id
            if state in {"Failed", "Error"}:
                raise RuntimeError(f"Gateway creation failed: {state}")
        time.sleep(5)
    raise RuntimeError("API gateway did not become ready in 10 minutes.")


def _create_gateway_service(apig: Any, gateway_id: str) -> str:
    from volcenginesdkapig import (
        AuthSpecForCreateGatewayServiceInput,
        CreateGatewayServiceRequest,
    )

    response = apig.apig_client.create_gateway_service(
        CreateGatewayServiceRequest(
            auth_spec=AuthSpecForCreateGatewayServiceInput(enable=False),
            comments=_RESOURCE_NOTE,
            gateway_id=gateway_id,
            protocol=["HTTP", "HTTPS"],
            service_name=_GATEWAY_SERVICE_NAME,
        ),
        async_req=True,
    ).get()
    return str(response.id)


def _create_gateway_upstream(apig: Any, function_id: str, gateway_id: str) -> str:
    from volcenginesdkapig import (
        CreateUpstreamRequest,
        UpstreamSpecForCreateUpstreamInput,
        VeFaasForCreateUpstreamInput,
    )

    response = apig.apig_client.create_upstream(
        CreateUpstreamRequest(
            comments=_RESOURCE_NOTE,
            gateway_id=gateway_id,
            name=_GATEWAY_UPSTREAM_NAME,
            source_type="VeFaas",
            upstream_spec=UpstreamSpecForCreateUpstreamInput(
                ve_faas=VeFaasForCreateUpstreamInput(function_id=function_id)
            ),
        ),
        async_req=True,
    ).get()
    return str(response.id)


def _ensure_gateway_binding(service: Any, function_id: str) -> str:
    """Expose one Function through a service on the fixed serverless gateway."""
    from volcenginesdkapig import (
        ListGatewayServicesRequest,
        ListGatewaysRequest,
        ListUpstreamsRequest,
    )
    from volcenginesdkapig20221112 import (
        AdvancedSettingForUpdateRouteInput,
        ListRoutesRequest,
        MatchRuleForUpdateRouteInput,
        PathForUpdateRouteInput,
        TimeoutSettingForUpdateRouteInput,
        UpdateRouteRequest,
        UpstreamListForUpdateRouteInput,
    )

    apig = service.apig_client
    gateway_response = apig.apig_client.list_gateways(
        ListGatewaysRequest(page_number=1, page_size=100), async_req=True
    ).get()
    gateways = list(getattr(gateway_response, "items", []) or [])
    gateway = _find_named(gateways, _GATEWAY_NAME)
    if gateway is None:
        gateway = _find_reusable_serverless_gateway(gateways)
        if gateway is None:
            gateway_id = _create_serverless_gateway(apig)
        else:
            gateway_id = str(gateway.id)
    else:
        if getattr(gateway, "type", None) != "serverless":
            raise RuntimeError(f"Gateway {_GATEWAY_NAME} is not serverless.")
        gateway_state = getattr(gateway, "status", None) or getattr(
            gateway, "message", None
        )
        if gateway_state != "Running":
            raise RuntimeError(f"Gateway {_GATEWAY_NAME} is not running.")
        gateway_id = str(gateway.id)

    service_response = apig.apig_client.list_gateway_services(
        ListGatewayServicesRequest(
            gateway_id=gateway_id,
            page_number=1,
            page_size=100,
        ),
        async_req=True,
    ).get()
    gateway_service = _find_named(
        list(getattr(service_response, "items", []) or []),
        _GATEWAY_SERVICE_NAME,
    )
    if gateway_service is None:
        service_id = _create_gateway_service(apig, gateway_id)
    else:
        service_id = str(gateway_service.id)

    upstream_response = apig.apig_client.list_upstreams(
        ListUpstreamsRequest(
            gateway_id=gateway_id,
            page_number=1,
            page_size=100,
        ),
        async_req=True,
    ).get()
    upstream = _find_named(
        list(getattr(upstream_response, "items", []) or []),
        _GATEWAY_UPSTREAM_NAME,
    )
    if upstream is None:
        upstream_id = _create_gateway_upstream(apig, function_id, gateway_id)
    else:
        upstream_payload = upstream.to_dict()
        if function_id not in json.dumps(upstream_payload):
            raise RuntimeError(
                f"Upstream {_GATEWAY_UPSTREAM_NAME} targets another Function."
            )
        upstream_id = str(upstream.id)

    route_response = apig.apig_20221112_client.list_routes(
        ListRoutesRequest(
            service_id=service_id,
            page_number=1,
            page_size=100,
        ),
        async_req=True,
    ).get()
    route = _find_named(
        list(getattr(route_response, "items", []) or []),
        _GATEWAY_ROUTE_NAME,
    )
    if route is None:
        route_id = apig.create_gateway_service_routes(
            service_id,
            upstream_id,
            _GATEWAY_ROUTE_NAME,
            {
                "match_content": "/",
                "match_type": "Prefix",
                "match_method": ["GET", "POST"],
            },
        )
    else:
        route_payload = route.to_dict()
        if upstream_id not in json.dumps(route_payload):
            raise RuntimeError(f"Route {_GATEWAY_ROUTE_NAME} targets another upstream.")
        route_id = str(route.id)
    apig.apig_20221112_client.update_route(
        UpdateRouteRequest(
            id=route_id,
            name=_GATEWAY_ROUTE_NAME,
            enable=True,
            priority=1,
            match_rule=MatchRuleForUpdateRouteInput(
                method=["GET", "POST"],
                path=PathForUpdateRouteInput(
                    match_content="/",
                    match_type="Prefix",
                ),
            ),
            upstream_list=[
                UpstreamListForUpdateRouteInput(
                    upstream_id=upstream_id,
                    weight=1,
                )
            ],
            advanced_setting=AdvancedSettingForUpdateRouteInput(
                timeout_setting=TimeoutSettingForUpdateRouteInput(
                    enable=True,
                    timeout=_GATEWAY_TIMEOUT_MILLISECONDS,
                )
            ),
        ),
        async_req=True,
    ).get()

    for _ in range(60):
        service_response = apig.apig_client.list_gateway_services(
            ListGatewayServicesRequest(
                gateway_id=gateway_id,
                page_number=1,
                page_size=100,
            ),
            async_req=True,
        ).get()
        gateway_service = _find_named(
            list(getattr(service_response, "items", []) or []),
            _GATEWAY_SERVICE_NAME,
        )
        if gateway_service is not None:
            endpoint = _https_endpoint(gateway_service)
            state = getattr(gateway_service, "status", None) or getattr(
                gateway_service, "message", None
            )
            if state == "Running" and endpoint:
                return endpoint
        time.sleep(5)
    raise RuntimeError("API gateway service did not become ready in 5 minutes.")


def stage(source: Path, destination: Path) -> None:
    target = destination / "frontend/service/studio_release_notifier"
    target.mkdir(parents=True)
    for relative in ("frontend/__init__.py", "frontend/service/__init__.py"):
        shutil.copy2(source / relative, destination / relative)
    for name in ("app.py", "__init__.py"):
        shutil.copy2(
            source / "frontend/service/studio_release_notifier" / name, target / name
        )
    shutil.copy2(
        source / "frontend/service/studio_release_notifier/run.sh", destination
    )
    packages = destination / "site-packages"
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--target",
            str(packages),
            "--python-version",
            "3.12",
            "--python-platform",
            "x86_64-manylinux2014",
            "--link-mode",
            "copy",
            "fastapi>=0.115,<1",
            "httpx>=0.27,<1",
            "uvicorn>=0.34,<1",
            "requests>=2.19.1,<3",
            "six",
            "pytz",
            "Deprecated>=1.2.13,<2",
        ],
        check=True,
    )
    for name in ("tos", "crcmod"):
        module = importlib.util.find_spec(name)
        if module is None or module.submodule_search_locations is None:
            raise RuntimeError(f"Missing packaging dependency: {name}")
        shutil.copytree(
            Path(next(iter(module.submodule_search_locations))),
            packages / name,
            ignore=shutil.ignore_patterns("*.so", "*.dylib", "__pycache__"),
        )


def main() -> None:
    from volcenginesdkvefaas import (
        CreateFunctionRequest,
        EnvForCreateFunctionInput,
        UpdateFunctionRequest,
        TagForCreateFunctionInput,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    environment = {
        name: os.environ[name]
        for name in (
            "FEISHU_APP_ID",
            "FEISHU_APP_SECRET",
            "STUDIO_RELEASE_WEBHOOK_KEY",
            "NOTIFIER_PREVIEW_USER_ID",
        )
    }
    environment.update(
        NOTIFIER_TOS_BUCKET="veadk-studio", NOTIFIER_TOS_REGION="cn-beijing"
    )
    if len(environment["STUDIO_RELEASE_WEBHOOK_KEY"]) < 32:
        raise ValueError("Webhook key must contain at least 32 characters")
    access_key, secret_key = (
        os.environ["VOLCENGINE_ACCESS_KEY"],
        os.environ["VOLCENGINE_SECRET_KEY"],
    )
    session = os.environ.get("VOLCENGINE_SESSION_TOKEN", "")
    role = _ensure_runtime_role(
        access_key, secret_key, provider="volcengine", session_token=session
    )
    engine = CloudAgentEngine(
        volcengine_access_key=access_key,
        volcengine_secret_key=secret_key,
        volcengine_session_token=session,
        region="cn-beijing",
        provider="volcengine",
    )
    service = engine._vefaas_service
    with tempfile.TemporaryDirectory(prefix="studio-release-notifier-") as directory:
        root = Path(directory)
        stage(args.source_root.resolve(), root)
        function = _find_function(service)
        if function is None:
            result: Any = service.client.create_function(
                CreateFunctionRequest(
                    name=_FUNCTION_NAME,
                    description=_RESOURCE_NOTE,
                    runtime="native-python3.12/v1",
                    command="./run.sh",
                    port=8000,
                    cpu_milli=1000,
                    memory_mb=2048,
                    max_concurrency=10,
                    request_timeout=180,
                    initializer_sec=60,
                    role=role,
                    project_name="default",
                    tags=[TagForCreateFunctionInput(key="note", value="勿删")],
                    envs=[
                        EnvForCreateFunctionInput(key=k, value=v)
                        for k, v in environment.items()
                    ],
                )
            )
            function_id = str(result.id)
            print(
                json.dumps({"functionId": function_id, "stage": "upload"}), flush=True
            )
            _retry_code_upload(
                lambda: service._upload_and_mount_code(function_id, str(root))
            )
        else:
            function_id = str(function.id)
            service.client.update_function(
                UpdateFunctionRequest(
                    id=function_id, description=_RESOURCE_NOTE, role=role
                )
            )
            _retry_code_upload(
                lambda: service._replace_application_code_bundle(
                    function_id=function_id,
                    path=str(root),
                    environment_overrides=environment,
                )
            )
        _release_function(service, function_id)
        endpoint = _ensure_gateway_binding(service, function_id)
        print(
            json.dumps(
                {
                    "functionId": function_id,
                    "endpoint": endpoint,
                    "description": _RESOURCE_NOTE,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
