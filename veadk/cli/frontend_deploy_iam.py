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

"""Ensure the IAM role the VeFaaS-hosted frontend runs as.

Volcengine IAM has no inline role policy, so the role is built as: CreatePolicy
(custom) + CreateRole (trust ``vefaas``) + AttachRolePolicy. The whole thing is
idempotent — a fixed role/policy name is reused across re-deploys.
"""

import json
from typing import Any

from veadk.cli.frontend_deploy_policy import (
    FRONTEND_DEPLOY_POLICY,
    FRONTEND_DEPLOY_SYSTEM_POLICIES,
    FRONTEND_DEPLOY_TRUST_POLICY,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_ROLE_NAME = "VeADKFrontendServiceRole"
DEFAULT_POLICY_NAME = "VeADKFrontendPolicy"


def _result(resp: dict) -> dict:
    """Extract ``Result`` from a Volcengine response, raising on an API error."""
    meta = (resp or {}).get("ResponseMetadata", {}) or {}
    if meta.get("Error"):
        raise RuntimeError(meta["Error"].get("Message") or str(meta["Error"]))
    return (resp or {}).get("Result", {}) or {}


def _role_trn(result: dict) -> str | None:
    """Pull the role TRN out of a GetRole/CreateRole Result (shape varies)."""
    role = result.get("Role") or result
    return role.get("Trn") or role.get("trn")


def _ensure_role_policies(svc: Any, role_name: str, policy_name: str) -> None:
    """Attach the current custom policy and any missing system policies."""
    result = _result(svc.list_attached_role_policies({"RoleName": role_name}))
    attached = {
        policy["PolicyName"]
        for policy in result.get("AttachedPolicyMetadata", [])
        if policy.get("PolicyName")
    }
    if policy_name not in attached:
        _result(
            svc.attach_role_policy(
                {
                    "RoleName": role_name,
                    "PolicyName": policy_name,
                    "PolicyType": "Custom",
                }
            )
        )
    for policy_name in FRONTEND_DEPLOY_SYSTEM_POLICIES:
        if policy_name in attached:
            continue
        _result(
            svc.attach_role_policy(
                {
                    "RoleName": role_name,
                    "PolicyName": policy_name,
                    "PolicyType": "System",
                }
            )
        )
        logger.info(f"Attached system policy {policy_name} to role {role_name}")


def _ensure_custom_policy(svc: Any, policy_name: str) -> None:
    """Create the runtime policy or replace its document when it exists."""
    policy_document = json.dumps(FRONTEND_DEPLOY_POLICY)
    try:
        _result(
            svc.update_policy(
                {
                    "PolicyName": policy_name,
                    "NewPolicyDocument": policy_document,
                }
            )
        )
        logger.info(f"Updated IAM policy {policy_name}")
    except Exception as update_error:
        logger.info(f"IAM policy {policy_name} is not updatable yet: {update_error}")
        try:
            _result(
                svc.create_policy(
                    {
                        "PolicyName": policy_name,
                        "PolicyDocument": policy_document,
                        "Description": "VeADK frontend deploy permissions",
                    }
                )
            )
            logger.info(f"Created IAM policy {policy_name}")
        except Exception as create_error:
            raise RuntimeError(
                f"Could not create or update IAM policy {policy_name}: {create_error}"
            ) from create_error
    _verify_custom_policy(svc, policy_name)


def _verify_custom_policy(svc: Any, policy_name: str) -> None:
    """Fail fast unless IAM serves every action required by the frontend."""
    result = _result(
        svc.get_policy({"PolicyName": policy_name, "PolicyType": "Custom"})
    )
    policy = result.get("Policy", result)
    document = policy.get("PolicyDocument")
    if isinstance(document, str):
        document = json.loads(document)
    if not isinstance(document, dict):
        raise RuntimeError(f"IAM policy {policy_name} has no readable document")

    expected_actions = set(FRONTEND_DEPLOY_POLICY["Statement"][0]["Action"])
    actual_actions = {
        action
        for statement in document.get("Statement", [])
        for action in statement.get("Action", [])
    }
    missing = expected_actions - actual_actions
    if missing:
        raise RuntimeError(
            f"IAM policy {policy_name} is missing required actions: "
            + ", ".join(sorted(missing))
        )


def ensure_frontend_role(
    access_key: str,
    secret_key: str,
    role_name: str = DEFAULT_ROLE_NAME,
    policy_name: str = DEFAULT_POLICY_NAME,
    session_token: str = "",
) -> str:
    """Get-or-create the frontend's IAM role and return its TRN.

    IAM is a global service, so region is irrelevant here. Safe to call
    repeatedly: an existing role is reused, and create/attach errors for
    already-existing resources are tolerated.
    """
    from volcengine.iam.IamService import IamService

    svc = IamService()
    svc.set_ak(access_key)
    svc.set_sk(secret_key)
    if session_token:
        svc.set_session_token(session_token)
    _ensure_custom_policy(svc, policy_name)

    # Reuse an existing role if present.
    try:
        existing = _result(svc.get_role({"RoleName": role_name}))
    except Exception as e:
        logger.info(f"Role {role_name} not found, creating it: {e}")
    else:
        trn = _role_trn(existing)
        if trn:
            logger.info(f"Reusing existing IAM role {role_name} ({trn})")
            _ensure_role_policies(svc, role_name, policy_name)
            return trn

    # Create the role with the vefaas trust relationship.
    created = _result(
        svc.create_role(
            {
                "RoleName": role_name,
                "TrustPolicyDocument": json.dumps(FRONTEND_DEPLOY_TRUST_POLICY),
                "Description": "VeADK frontend VeFaaS runtime role",
            }
        )
    )

    trn = _role_trn(created)
    if not trn:
        # CreateRole didn't echo the TRN — read it back.
        trn = _role_trn(_result(svc.get_role({"RoleName": role_name})))
    if not trn:
        raise RuntimeError(f"Could not resolve TRN for role {role_name}")
    _ensure_role_policies(svc, role_name, policy_name)
    logger.info(f"Ensured IAM role {role_name} ({trn})")
    return trn
