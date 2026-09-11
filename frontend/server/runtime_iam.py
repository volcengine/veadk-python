# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

"""Select IAM roles for new Studio Agent Runtimes"""

from __future__ import annotations

import json
import os
import threading
from typing import Any

from veadk.utils.cloud_provider import (
    DEFAULT_CLOUD_PROVIDER,
    CloudProvider,
    iam_openapi_host,
)

DEFAULT_RUNTIME_POLICY = "AgentKitDefaultRuntimeAccess"
DEFAULT_RUNTIME_ROLE = "AgentKit_Runtime_Default_ServiceRole"
_ROLE_PAGE_SIZE = 100
_ROLE_LOCK = threading.Lock()
_LEGACY_RUNTIME_POLICIES = frozenset(
    {
        "cloudcontrolreadonlyaccess",
        "agentkittosaccess",
        "torchlightapifullaccess",
        "llmshieldprotectsdkaccess",
        "agentkittoolaccess",
        "idreadonlyaccess",
        "mem0readonlyaccess",
        "agentkitruntimeaccess",
    }
)


def _result(response: dict[str, Any]) -> dict[str, Any]:
    error = (response.get("ResponseMetadata") or {}).get("Error")
    if error:
        raise RuntimeError(error.get("Message") or str(error))
    result = response.get("Result", {})
    if not isinstance(result, dict):
        raise RuntimeError("IAM response is missing Result")
    return result


def _role_policies(iam: Any, name: str) -> frozenset[str]:
    policies = _result(iam.list_attached_role_policies({"RoleName": name})).get(
        "AttachedPolicyMetadata"
    )
    if not isinstance(policies, list):
        raise RuntimeError("IAM returned an invalid role policy list")
    return frozenset(
        str(policy.get("PolicyName") or "").casefold()
        for policy in policies
        if policy.get("PolicyType") == "System"
    )


def _is_runtime_role(policies: frozenset[str]) -> bool:
    return (
        DEFAULT_RUNTIME_POLICY.casefold() in policies
        or _LEGACY_RUNTIME_POLICIES <= policies
    )


def _error_code(value: object) -> str:
    if isinstance(value, dict):
        return str(
            ((value.get("ResponseMetadata") or {}).get("Error") or {}).get("Code") or ""
        )
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return ""
    return _error_code(parsed)


def _get_role(iam: Any, name: str) -> dict[str, Any] | None:
    try:
        response = iam.get_role({"RoleName": name})
    except Exception as error:
        if _error_code(error) == "RoleNotExist":
            return None
        raise
    if _error_code(response) == "RoleNotExist":
        return None
    role = _result(response).get("Role")
    if not isinstance(role, dict) or role.get("RoleName") != name:
        raise RuntimeError("IAM returned an invalid role")
    return role


def _find_reusable_role(iam: Any) -> str | None:
    offset = 0
    while True:
        page = _result(iam.list_roles({"Limit": _ROLE_PAGE_SIZE, "Offset": offset}))
        roles = page.get("RoleMetadata")
        total = page.get("Total")
        if not isinstance(roles, list) or not isinstance(total, int) or total < 0:
            raise RuntimeError("IAM returned an invalid role list")
        for role in roles:
            name = role.get("RoleName")
            if not isinstance(name, str) or not name.strip():
                raise RuntimeError("IAM role is missing RoleName")
            if _is_runtime_role(_role_policies(iam, name)):
                return name
        offset += len(roles)
        if offset >= total:
            return None
        if not roles:
            raise RuntimeError("IAM returned an incomplete role list")


def ensure_runtime_role(
    *,
    access_key: str,
    secret_key: str,
    session_token: str | None = None,
    provider: CloudProvider = DEFAULT_CLOUD_PROVIDER,
) -> str:
    """Reuse a matching role, or create the shared default Runtime role.

    Both current and legacy AgentKit policy layouts are recognized so evaluation
    attempts never create one IAM role per temporary Runtime.
    """
    with _ROLE_LOCK:
        return _ensure_runtime_role(
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
            provider=provider,
        )


def _ensure_runtime_role(
    *,
    access_key: str,
    secret_key: str,
    session_token: str | None,
    provider: CloudProvider,
) -> str:
    from volcengine.iam.IamService import IamService

    iam = IamService()
    iam.set_ak(access_key)
    iam.set_sk(secret_key)
    iam.set_host(iam_openapi_host(provider))
    iam.set_scheme("https")
    if session_token:
        iam.set_session_token(session_token)

    default = _get_role(iam, DEFAULT_RUNTIME_ROLE)
    if default is not None:
        policies = _role_policies(iam, DEFAULT_RUNTIME_ROLE)
        if not _is_runtime_role(policies):
            _result(
                iam.attach_role_policy(
                    {
                        "RoleName": DEFAULT_RUNTIME_ROLE,
                        "PolicyName": DEFAULT_RUNTIME_POLICY,
                        "PolicyType": "System",
                    }
                )
            )
        return DEFAULT_RUNTIME_ROLE

    existing = _find_reusable_role(iam)
    if existing is not None:
        return existing

    service_code = (
        os.getenv("VOLCENGINE_AGENTKIT_SERVICE")
        or os.getenv("VOLC_AGENTKIT_SERVICE")
        or os.getenv("BYTEPLUS_AGENTKIT_SERVICE")
        or ""
    ).lower()
    trust_policy = {
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["sts:AssumeRole"],
                "Principal": {
                    "Service": ["vefaas_dev" if "stg" in service_code else "vefaas"]
                },
            }
        ]
    }
    _result(
        iam.create_role(
            {
                "RoleName": DEFAULT_RUNTIME_ROLE,
                "TrustPolicyDocument": json.dumps(trust_policy),
            }
        )
    )
    _result(
        iam.attach_role_policy(
            {
                "RoleName": DEFAULT_RUNTIME_ROLE,
                "PolicyName": DEFAULT_RUNTIME_POLICY,
                "PolicyType": "System",
            }
        )
    )
    return DEFAULT_RUNTIME_ROLE
