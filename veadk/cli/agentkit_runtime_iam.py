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

"""IAM policy synchronization for AgentKit-created Runtime roles."""

from typing import Any

from veadk.utils.cloud_provider import (
    DEFAULT_CLOUD_PROVIDER,
    CloudProvider,
    iam_openapi_host,
)

AGENTKIT_RUNTIME_FULL_ACCESS_POLICY = "AgentKitFullAccess"
_AGENTKIT_DEFAULT_RUNTIME_ROLE_PREFIXES = (
    "AgentKit_Runtime_Default_ServiceRole",
    "AgentKit-Runtime-Default-ServiceRole",
)


def _result(response: dict[str, Any]) -> dict[str, Any]:
    metadata = response.get("ResponseMetadata", {}) or {}
    if metadata.get("Error"):
        error = metadata["Error"]
        raise RuntimeError(error.get("Message") or str(error))
    return response.get("Result", {}) or {}


def is_agentkit_default_runtime_role(role_name: str) -> bool:
    """Return whether AgentKit generated the Runtime role automatically."""
    normalized = str(role_name or "").strip().rsplit("/", 1)[-1]
    return normalized.startswith(_AGENTKIT_DEFAULT_RUNTIME_ROLE_PREFIXES)


def ensure_quick_runtime_full_access(
    role_name: str,
    *,
    access_key: str,
    secret_key: str,
    session_token: str = "",
    provider: CloudProvider = DEFAULT_CLOUD_PROVIDER,
) -> bool:
    """Attach AgentKitFullAccess to a quick Runtime's generated default role.

    Customer-managed Runtime roles are never modified. The return value tells
    the caller whether the supplied role is an AgentKit-generated default role.
    """
    normalized = str(role_name or "").strip().rsplit("/", 1)[-1]
    if not is_agentkit_default_runtime_role(normalized):
        return False

    from volcengine.iam.IamService import IamService

    iam = IamService()
    iam.set_ak(access_key)
    iam.set_sk(secret_key)
    iam.set_host(iam_openapi_host(provider))
    if provider == "byteplus":
        iam.set_scheme("https")
    if session_token:
        iam.set_session_token(session_token)

    attached = _result(iam.list_attached_role_policies({"RoleName": normalized})).get(
        "AttachedPolicyMetadata", []
    )
    if any(
        str(policy.get("PolicyName") or "") == AGENTKIT_RUNTIME_FULL_ACCESS_POLICY
        for policy in attached
    ):
        return True
    _result(
        iam.attach_role_policy(
            {
                "RoleName": normalized,
                "PolicyName": AGENTKIT_RUNTIME_FULL_ACCESS_POLICY,
                "PolicyType": "System",
            }
        )
    )
    return True
