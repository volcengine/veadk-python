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

"""Provision the IAM role required by Studio's VeFaaS deployment."""

import json
from typing import Any

import click

from veadk.cli.studio_deploy_serverless_policy import (
    CUSTOM_POLICY,
    SYSTEM_POLICIES,
    TRUST_POLICY,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

ROLE_NAME = "ServerlessApplicationRole"
CUSTOM_POLICY_NAME = "vefaas_full_access"


def _result(response: dict) -> dict:
    """Extract a successful IAM result and fail on an API error."""
    error = (response.get("ResponseMetadata", {}) or {}).get("Error")
    if error:
        code = error.get("Code", "IAMError")
        message = error.get("Message", str(error))
        raise RuntimeError(f"{code}: {message}")
    return response.get("Result", {}) or {}


def _exception_error_code(error: Exception) -> str | None:
    """Read the IAM error code exposed as JSON by the legacy SDK."""
    try:
        payload = json.loads(str(error))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    metadata = payload.get("ResponseMetadata", {}) or {}
    iam_error = metadata.get("Error", {}) or {}
    return iam_error.get("Code")


def _get_role(service: Any) -> dict | None:
    """Return the deployment role, or ``None`` when it does not exist."""
    try:
        response = service.get_role({"RoleName": ROLE_NAME})
    except Exception as error:
        # IamService exposes all HTTP failures as plain Exception instances.
        if _exception_error_code(error) == "RoleNotExist":
            return None
        raise
    return _result(response)


def _get_custom_policy(service: Any) -> dict | None:
    """Return the required custom policy, or ``None`` when absent."""
    try:
        response = service.get_policy(
            {"PolicyName": CUSTOM_POLICY_NAME, "PolicyType": "Custom"}
        )
    except Exception as error:
        # IamService exposes all HTTP failures as plain Exception instances.
        if _exception_error_code(error) == "PolicyNotExist":
            return None
        raise
    return _result(response)


def _ensure_custom_policy(service: Any) -> None:
    """Create the custom VeFaaS policy when it is missing."""
    if _get_custom_policy(service) is not None:
        return
    _result(
        service.create_policy(
            {
                "PolicyName": CUSTOM_POLICY_NAME,
                "PolicyDocument": json.dumps(CUSTOM_POLICY),
                "Description": "VeFaaS serverless application deployment permissions",
            }
        )
    )
    logger.info(f"Created IAM policy {CUSTOM_POLICY_NAME}.")


def _attach_role_policies(service: Any) -> None:
    """Attach all policies required by a newly created role."""
    policies = ((CUSTOM_POLICY_NAME, "Custom"),) + tuple(
        (policy_name, "System") for policy_name in SYSTEM_POLICIES
    )
    for policy_name, policy_type in policies:
        _result(
            service.attach_role_policy(
                {
                    "RoleName": ROLE_NAME,
                    "PolicyName": policy_name,
                    "PolicyType": policy_type,
                }
            )
        )
        logger.info(f"Attached IAM policy {policy_name} to {ROLE_NAME}.")


def ensure_serverless_application_role(
    access_key: str,
    secret_key: str,
) -> bool:
    """Ensure Studio's VeFaaS deployment role has its required policies.

    Args:
        access_key: Volcengine access key used for IAM operations.
        secret_key: Volcengine secret key used for IAM operations.

    Returns:
        Whether the role was created by this call.
    """
    from volcengine.iam.IamService import IamService

    service = IamService()
    service.set_ak(access_key)
    service.set_sk(secret_key)

    if _get_role(service) is not None:
        logger.info(f"IAM role {ROLE_NAME} is ready.")
        return False

    click.secho(
        f"IAM role {ROLE_NAME} was not found; creating it automatically.",
        fg="yellow",
    )

    _ensure_custom_policy(service)
    _result(
        service.create_role(
            {
                "RoleName": ROLE_NAME,
                "TrustPolicyDocument": json.dumps(TRUST_POLICY),
                "Description": "VeFaaS serverless application role",
                "MaxSessionDuration": 43200,
            }
        )
    )
    _attach_role_policies(service)
    click.echo(
        f"IAM role {ROLE_NAME} was created automatically with required policies."
    )
    return True
