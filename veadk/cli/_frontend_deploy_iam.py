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

from veadk.cli._frontend_deploy_policy import (
    FRONTEND_DEPLOY_POLICY,
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


def ensure_frontend_role(
    access_key: str,
    secret_key: str,
    role_name: str = DEFAULT_ROLE_NAME,
    policy_name: str = DEFAULT_POLICY_NAME,
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

    # Reuse an existing role if present.
    try:
        existing = _result(svc.get_role({"RoleName": role_name}))
        trn = _role_trn(existing)
        if trn:
            logger.info(f"Reusing existing IAM role {role_name} ({trn})")
            return trn
    except Exception as e:
        logger.info(f"Role {role_name} not found, creating it: {e}")

    # Create the custom policy (tolerate "already exists").
    try:
        svc.create_policy(
            {
                "PolicyName": policy_name,
                "PolicyDocument": json.dumps(FRONTEND_DEPLOY_POLICY),
                "Description": "VeADK frontend deploy permissions",
            }
        )
        logger.info(f"Created IAM policy {policy_name}")
    except Exception as e:
        logger.info(f"CreatePolicy {policy_name} skipped/failed (may exist): {e}")

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

    # Attach the policy to the role (tolerate "already attached").
    try:
        svc.attach_role_policy(
            {
                "RoleName": role_name,
                "PolicyName": policy_name,
                "PolicyType": "Custom",
            }
        )
        logger.info(f"Attached policy {policy_name} to role {role_name}")
    except Exception as e:
        logger.info(f"AttachRolePolicy skipped/failed (may be attached): {e}")

    trn = _role_trn(created)
    if not trn:
        # CreateRole didn't echo the TRN — read it back.
        trn = _role_trn(_result(svc.get_role({"RoleName": role_name})))
    if not trn:
        raise RuntimeError(f"Could not resolve TRN for role {role_name}")
    logger.info(f"Ensured IAM role {role_name} ({trn})")
    return trn
