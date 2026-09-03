# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""VeStack IAM role provisioning for a VeFaaS-hosted Studio."""

from typing import Any

from veadk.cli.frontend_deploy_iam import (
    DEFAULT_POLICY_NAME,
    DEFAULT_ROLE_NAME,
    _ensure_frontend_role,
    _result,
)
from veadk.cli.frontend_deploy_policy import FRONTEND_DEPLOY_SYSTEM_POLICIES
from veadk.utils.cloud_provider import DEFAULT_CLOUD_PROVIDER, CloudProvider
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def _ensure_role_policies_vestack(
    svc: Any,
    role_name: str,
    policy_name: str,
) -> None:
    """Attach policies available in the VeStack IAM policy catalog."""
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
    for system_policy_name in FRONTEND_DEPLOY_SYSTEM_POLICIES:
        if system_policy_name in attached:
            continue
        try:
            _result(
                svc.attach_role_policy(
                    {
                        "RoleName": role_name,
                        "PolicyName": system_policy_name,
                        "PolicyType": "System",
                    }
                )
            )
        except Exception as error:
            detail = str(error)
            if "PolicyNotExist" not in detail and "Policy does not exist" not in detail:
                raise
            logger.warning(
                "VeStack system policy %s is unavailable; the Studio custom "
                "policy remains attached.",
                system_policy_name,
            )
            continue
        logger.info(
            "Attached VeStack system policy %s to role %s",
            system_policy_name,
            role_name,
        )


def ensure_frontend_role_vestack(
    access_key: str,
    secret_key: str,
    role_name: str = DEFAULT_ROLE_NAME,
    policy_name: str = DEFAULT_POLICY_NAME,
    session_token: str = "",
    provider: CloudProvider = DEFAULT_CLOUD_PROVIDER,
) -> str:
    """Get or create the Studio role using VeStack policy availability rules."""
    return _ensure_frontend_role(
        access_key,
        secret_key,
        role_name,
        policy_name,
        session_token,
        provider,
        ensure_role_policies=_ensure_role_policies_vestack,
    )
