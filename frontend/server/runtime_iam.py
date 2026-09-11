# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
# SPDX-License-Identifier: Apache-2.0

"""Select IAM roles for new Studio Agent Runtimes"""

from __future__ import annotations

import json
import os
from typing import Any

from veadk.utils.cloud_provider import (
    DEFAULT_CLOUD_PROVIDER,
    CloudProvider,
    iam_openapi_host,
)

DEFAULT_RUNTIME_POLICY = "AgentKitDefaultRuntimeAccess"
_ROLE_PAGE_SIZE = 100


def _result(response: dict[str, Any]) -> dict[str, Any]:
    error = (response.get("ResponseMetadata") or {}).get("Error")
    if error:
        raise RuntimeError(error.get("Message") or str(error))
    result = response.get("Result", {})
    if not isinstance(result, dict):
        raise RuntimeError("IAM response is missing Result")
    return result


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
            policies = _result(iam.list_attached_role_policies({"RoleName": name})).get(
                "AttachedPolicyMetadata"
            )
            if not isinstance(policies, list):
                raise RuntimeError("IAM returned an invalid role policy list")
            if any(
                policy.get("PolicyName") == DEFAULT_RUNTIME_POLICY
                and policy.get("PolicyType") == "System"
                for policy in policies
            ):
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
    """Reuse a matching role, or create one with only the default runtime policy

    Called under Studio's deployment lock so concurrent local deployments can
    reuse the role created by the previous deployment
    """
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

    from agentkit.utils.misc import generate_runtime_role_name

    name = generate_runtime_role_name()
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
            {"RoleName": name, "TrustPolicyDocument": json.dumps(trust_policy)}
        )
    )
    _result(
        iam.attach_role_policy(
            {
                "RoleName": name,
                "PolicyName": DEFAULT_RUNTIME_POLICY,
                "PolicyType": "System",
            }
        )
    )
    return name
