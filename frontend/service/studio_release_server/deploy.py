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

"""Deploy the Studio release server to VeFaaS and configure GitHub secrets."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import veadk.config
from veadk.cli.studio_release import STUDIO_RELEASE_REGION
from veadk.cloud.cloud_agent_engine import CloudAgentEngine

_APPLICATION_NAME = "veadk-studio-release-server"
_FUNCTION_NAME = f"{_APPLICATION_NAME}-fn"
_GATEWAY_NAME = "test-api-gateway"
_GATEWAY_SERVICE_NAME = "veadk-studio-release-server"
_GATEWAY_UPSTREAM_NAME = "veadk-studio-release-server"
_GATEWAY_ROUTE_NAME = "veadk-studio-release-server"
_GATEWAY_TIMEOUT_MILLISECONDS = 30 * 60 * 1000
_BUCKET = "veadk-studio"
_REGION = STUDIO_RELEASE_REGION
_RELEASE_PREFIX = "veadk/studio/main"
_JOB_PREFIX = "veadk/studio/release-server/jobs"
_REPOSITORY = "volcengine/veadk-python"
_ROLE_NAME = "VeADKStudioReleaseServerRole"
_POLICY_NAME = "VeADKStudioReleaseServerPolicy"
_NODE_VERSION = "22.17.0"
_NODE_ARCHIVE_NAME = f"node-v{_NODE_VERSION}-linux-x64.tar.xz"
_NODE_ARCHIVE_URL = (
    "https://registry.npmmirror.com/-/binary/node/"
    f"v{_NODE_VERSION}/{_NODE_ARCHIVE_NAME}"
)
_NODE_ARCHIVE_SHA256 = (
    "325c0f1261e0c61bcae369a1274028e9cfb7ab7949c05512c5b1e630f7e80e12"
)
_MAX_NODE_ARCHIVE_BYTES = 128 * 1024 * 1024

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
            "Action": [
                "tos:GetBucketInfo",
                "tos:GetObject",
                "tos:HeadObject",
                "tos:ListObjectsV2",
                "tos:PutObject",
                "tos:DeleteObject",
            ],
            "Resource": ["*"],
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


def _ensure_runtime_role(access_key: str, secret_key: str) -> str:
    """Create or refresh the minimal VeFaaS role used for TOS publishing."""
    from volcengine.iam.IamService import IamService

    iam = IamService()
    iam.set_ak(access_key)
    iam.set_sk(secret_key)
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
                        "Description": "Publish AgentKit Studio releases to TOS",
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
                    "Description": "AgentKit Studio release server runtime role",
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


def _stage_deployment(source_root: Path, destination: Path) -> None:
    """Create the minimal source bundle consumed by the native runtime."""
    service_source = source_root / "frontend" / "service" / "studio_release_server"
    service_destination = destination / "frontend" / "service" / "studio_release_server"
    service_destination.parent.mkdir(parents=True)
    shutil.copytree(
        service_source,
        service_destination,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "deploy.py",
            "deploy.sh",
            "requirements.txt",
            "run.sh",
            "runtime-wheel-requirements.txt",
        ),
    )
    shutil.copy2(
        source_root / "frontend" / "__init__.py",
        destination / "frontend" / "__init__.py",
    )
    shutil.copy2(
        source_root / "frontend" / "service" / "__init__.py",
        destination / "frontend" / "service" / "__init__.py",
    )
    _stage_node_archive(service_destination)
    deployment_root = service_source
    shutil.copy2(deployment_root / "requirements.txt", destination)
    wheel_requirements = destination / "runtime-wheel-requirements.txt"
    shutil.copy2(
        deployment_root / "runtime-wheel-requirements.txt",
        wheel_requirements,
    )
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv is required to assemble the VeFaaS bundle.")
    site_packages = destination / "site-packages"
    subprocess.run(
        [
            uv,
            "pip",
            "install",
            "--target",
            str(site_packages),
            "--python-version",
            "3.12",
            "--python-platform",
            "x86_64-manylinux2014",
            "--link-mode",
            "copy",
            "-r",
            str(wheel_requirements),
        ],
        check=True,
    )
    for package_name in ("tos", "crcmod"):
        package = importlib.util.find_spec(package_name)
        if package is None or package.submodule_search_locations is None:
            raise RuntimeError(f"{package_name} is required to assemble the bundle.")
        package_root = Path(next(iter(package.submodule_search_locations)))
        shutil.copytree(
            package_root,
            site_packages / package_name,
            ignore=shutil.ignore_patterns(
                "*.so",
                "*.dylib",
                "__pycache__",
            ),
        )
    (site_packages / ".installed").touch()
    run_script = destination / "run.sh"
    shutil.copy2(deployment_root / "run.sh", run_script)
    run_script.chmod(0o755)


def _stage_node_archive(service_destination: Path) -> None:
    """Bundle the pinned Linux Node toolchain for network-free cold builds."""
    with urllib.request.urlopen(_NODE_ARCHIVE_URL, timeout=120) as response:
        content = response.read(_MAX_NODE_ARCHIVE_BYTES + 1)
    if len(content) > _MAX_NODE_ARCHIVE_BYTES:
        raise ValueError("Node archive exceeds 128 MiB.")
    if hashlib.sha256(content).hexdigest() != _NODE_ARCHIVE_SHA256:
        raise ValueError("Node archive checksum does not match.")
    (service_destination / _NODE_ARCHIVE_NAME).write_bytes(content)


def _runtime_environment(api_key: str) -> dict[str, str]:
    return {
        "STUDIO_RELEASE_SERVER_API_KEY": api_key,
        "STUDIO_RELEASE_BUCKET": _BUCKET,
        "STUDIO_RELEASE_REGION": _REGION,
        "STUDIO_RELEASE_PREFIX": _RELEASE_PREFIX,
        "STUDIO_RELEASE_JOB_PREFIX": _JOB_PREFIX,
        "STUDIO_RELEASE_REPOSITORY": _REPOSITORY,
    }


def _find_named(items: list[Any], name: str) -> Any | None:
    matches = [item for item in items if getattr(item, "name", None) == name]
    if len(matches) > 1:
        raise RuntimeError(f"Multiple cloud resources are named {name}.")
    return matches[0] if matches else None


def _find_function_id(service: Any) -> str:
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
    function = _find_named(functions, _FUNCTION_NAME)
    return str(getattr(function, "id", "") or "")


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
        raise RuntimeError(f"Serverless gateway {_GATEWAY_NAME} does not exist.")
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
        service_id = apig.create_gateway_service(gateway_id, _GATEWAY_SERVICE_NAME)
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
        upstream_id = apig.create_vefaas_upstream(
            function_id, gateway_id, _GATEWAY_UPSTREAM_NAME
        )
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


def _deploy(source_root: Path, api_key: str, role_trn: str) -> tuple[str, str, str]:
    """Create or update the Function and bind it to an existing gateway."""
    engine = CloudAgentEngine(region=_REGION)
    service = engine._vefaas_service
    runtime_environment = _runtime_environment(api_key)
    with tempfile.TemporaryDirectory(prefix="studio_release_server_") as tmp:
        deployment_root = Path(tmp)
        _stage_deployment(source_root, deployment_root)
        app_id = service.find_app_id_by_name(_APPLICATION_NAME)
        function_id = _find_function_id(service)
        if function_id:
            service._replace_application_code_bundle(
                function_id=function_id,
                path=str(deployment_root),
                environment_overrides=runtime_environment,
            )
        else:
            original_environment = dict(veadk.config.veadk_environments)
            original_role = os.environ.get("IAM_ROLE")
            try:
                veadk.config.veadk_environments.clear()
                veadk.config.veadk_environments.update(runtime_environment)
                os.environ["IAM_ROLE"] = role_trn
                _, function_id = service._create_function(
                    _FUNCTION_NAME, str(deployment_root)
                )
            finally:
                veadk.config.veadk_environments.clear()
                veadk.config.veadk_environments.update(original_environment)
                if original_role is None:
                    os.environ.pop("IAM_ROLE", None)
                else:
                    os.environ["IAM_ROLE"] = original_role
        _release_function(service, function_id)
        endpoint = _ensure_gateway_binding(service, function_id)
        return endpoint, app_id or "", function_id


def _wait_for_health(endpoint: str, api_key: str) -> None:
    ready_request = urllib.request.Request(
        f"{endpoint}/readyz",
        headers={"X-API-Key": api_key},
    )
    for _ in range(60):
        try:
            with urllib.request.urlopen(ready_request, timeout=10) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(5)
    raise RuntimeError("Release server readiness check failed for 5 minutes.")


def _validate_github_secret_access() -> None:
    """Fail before cloud changes if GitHub Secrets cannot be updated."""
    completed = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{_REPOSITORY}/actions/secrets/public-key",
            "--silent",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "GitHub Secrets preflight failed; no cloud resources were changed: "
            f"{completed.stderr}"
        )


def _set_github_secret(name: str, value: str) -> None:
    completed = subprocess.run(
        ["gh", "secret", "set", name, "--repo", _REPOSITORY],
        input=value,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Could not set GitHub secret {name}: {completed.stderr}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--skip-github-secrets",
        action="store_true",
        help="Deploy without changing repository secrets.",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    source_root = args.source_root.resolve()
    access_key = os.getenv("VOLCENGINE_ACCESS_KEY", "").strip()
    secret_key = os.getenv("VOLCENGINE_SECRET_KEY", "").strip()
    if not access_key or not secret_key:
        raise ValueError(
            "VOLCENGINE_ACCESS_KEY and VOLCENGINE_SECRET_KEY are required."
        )
    if not args.skip_github_secrets:
        _validate_github_secret_access()
    role_trn = _ensure_runtime_role(access_key, secret_key)
    api_key = secrets.token_urlsafe(48)
    endpoint, app_id, function_id = _deploy(source_root, api_key, role_trn)
    _wait_for_health(endpoint, api_key)
    if not args.skip_github_secrets:
        _set_github_secret("STUDIO_RELEASE_SERVER_URL", endpoint)
        _set_github_secret("STUDIO_RELEASE_SERVER_API_KEY", api_key)
    print(
        json.dumps(
            {
                "applicationName": _APPLICATION_NAME,
                "applicationId": app_id,
                "functionId": function_id,
                "endpoint": endpoint,
                "githubSecretsConfigured": not args.skip_github_secrets,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
