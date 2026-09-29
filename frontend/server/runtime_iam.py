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

"""Select IAM roles for new Studio Agent Runtimes"""

from __future__ import annotations

import json
import os
import secrets
import string
import threading
from typing import Any

from veadk.utils.cloud_provider import (
    DEFAULT_CLOUD_PROVIDER,
    CloudProvider,
    iam_openapi_host,
)

DEFAULT_RUNTIME_POLICY = "AgentKitDefaultRuntimeAccess"
DEFAULT_RUNTIME_ROLE = "AgentKit_Runtime_Default_ServiceRole"
_DEFAULT_RUNTIME_ROLE_PREFIX = f"{DEFAULT_RUNTIME_ROLE}_"
_ROLE_PAGE_SIZE = 100
_ROLE_NAME_ATTEMPTS = 10
_ROLE_SUFFIX_LENGTH = 7
_ROLE_SUFFIX_CHARS = string.ascii_lowercase + string.digits
_ROLE_LOCK = threading.Lock()
_ACCESS_DENIED_CODES = frozenset(
    {"AccessDenied", "AccessDeniedException", "UnauthorizedOperation"}
)


class _PolicyEntityLookupDenied(RuntimeError):
    """The caller cannot use IAM's reverse policy-to-role lookup."""


def _result(response: dict[str, Any]) -> dict[str, Any]:
    error = (response.get("ResponseMetadata") or {}).get("Error")
    if error:
        raise RuntimeError(error.get("Message") or str(error))
    result = response.get("Result", {})
    if not isinstance(result, dict):
        raise RuntimeError("IAM response is missing Result")
    return result


def _generate_runtime_role_name() -> str:
    suffix = "".join(
        secrets.choice(_ROLE_SUFFIX_CHARS) for _ in range(_ROLE_SUFFIX_LENGTH)
    )
    return f"{_DEFAULT_RUNTIME_ROLE_PREFIX}{suffix}"


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


def _role_has_default_runtime_policy(iam: Any, name: str) -> bool:
    policies = _result(iam.list_attached_role_policies({"RoleName": name})).get(
        "AttachedPolicyMetadata"
    )
    if not isinstance(policies, list):
        raise RuntimeError("IAM returned an invalid role policy list")
    for policy in policies:
        if not isinstance(policy, dict):
            raise RuntimeError("IAM returned an invalid role policy")
        policy_name = policy.get("PolicyName")
        policy_type = policy.get("PolicyType")
        if not isinstance(policy_name, str) or not policy_name.strip():
            raise RuntimeError("IAM role policy is missing PolicyName")
        if not isinstance(policy_type, str) or not policy_type.strip():
            raise RuntimeError("IAM role policy is missing PolicyType")
        if (
            policy_type.casefold() == "system"
            and policy_name.casefold() == DEFAULT_RUNTIME_POLICY.casefold()
        ):
            return True
    return False


def _find_reusable_role_by_listing(iam: Any) -> str | None:
    offset = 0
    while True:
        page = _result(iam.list_roles({"Limit": _ROLE_PAGE_SIZE, "Offset": offset}))
        roles = page.get("RoleMetadata")
        total = page.get("Total")
        if not isinstance(roles, list) or not isinstance(total, int) or total < 0:
            raise RuntimeError("IAM returned an invalid role list")
        if not roles and offset < total:
            raise RuntimeError("IAM returned an incomplete role list")
        for role in roles:
            name = role.get("RoleName") if isinstance(role, dict) else None
            if not isinstance(name, str) or not name.strip():
                raise RuntimeError("IAM role is missing RoleName")
            if _role_has_default_runtime_policy(iam, name):
                return name
        offset += len(roles)
        if offset >= total:
            return None


def _find_reusable_role_by_policy(iam: Any) -> str | None:
    offset = 0
    while True:
        try:
            response = iam.list_entities_for_policy(
                {
                    "PolicyName": DEFAULT_RUNTIME_POLICY,
                    "PolicyType": "System",
                    "Limit": _ROLE_PAGE_SIZE,
                    "Offset": offset,
                }
            )
        except Exception as error:
            if _error_code(error) in _ACCESS_DENIED_CODES:
                raise _PolicyEntityLookupDenied from error
            raise
        if _error_code(response) in _ACCESS_DENIED_CODES:
            raise _PolicyEntityLookupDenied
        page = _result(response)
        roles = page.get("PolicyRoles")
        total = page.get("Total")
        if not isinstance(roles, list) or not isinstance(total, int) or total < 0:
            raise RuntimeError("IAM returned an invalid policy entity list")
        for role in roles:
            name = role.get("RoleName") if isinstance(role, dict) else None
            if not isinstance(name, str) or not name.strip():
                raise RuntimeError("IAM role is missing RoleName")
            return name
        offset += _ROLE_PAGE_SIZE
        if offset >= total:
            return None


def _find_reusable_role(iam: Any) -> str | None:
    try:
        return _find_reusable_role_by_policy(iam)
    except _PolicyEntityLookupDenied:
        return _find_reusable_role_by_listing(iam)


def ensure_runtime_role(
    *,
    access_key: str,
    secret_key: str,
    session_token: str | None = None,
    provider: CloudProvider = DEFAULT_CLOUD_PROVIDER,
) -> str:
    """Reuse a minimum-policy role, or create a collision-free Runtime role.

    Existing roles are authoritative and never mutated. Legacy AgentKit policy
    layouts are not sufficient for new Runtimes because the CLI requires the
    platform-managed default Runtime policy on an explicitly selected role.
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
    for _ in range(_ROLE_NAME_ATTEMPTS):
        role_name = _generate_runtime_role_name()
        if _get_role(iam, role_name) is not None:
            continue
        _result(
            iam.create_role(
                {
                    "RoleName": role_name,
                    "TrustPolicyDocument": json.dumps(trust_policy),
                }
            )
        )
        _result(
            iam.attach_role_policy(
                {
                    "RoleName": role_name,
                    "PolicyName": DEFAULT_RUNTIME_POLICY,
                    "PolicyType": "System",
                }
            )
        )
        return role_name
    raise RuntimeError("Unable to generate a unique AgentKit Runtime role name")
