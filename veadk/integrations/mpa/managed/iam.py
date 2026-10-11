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

"""Additively prepare the approved account-scoped MPA execution role."""

from __future__ import annotations

import asyncio
import json
import time

from .database import DeploymentError
from .diagnostics import classify_error

ROLE_NAME = "IDRoleForArkClawShareAgent"
POLICY_NAME = "VeADKMPARuntimeAccessV1"
SYSTEM_POLICIES = (
    "AgentKitSkillsSandboxAccess",
    "AgentKitToolAccess",
    "LLMShieldProtectSdkAccess",
    "Mem0ReadOnlyAccess",
    "AgentKitRuntimeAccess",
    "AgentKitTosAccess",
    "CloudControlReadOnlyAccess",
    "TorchlightApiFullAccess",
    "IDReadOnlyAccess",
    "VikingdbFullAccess",
    "APMPlusServerDataExportRolePolicy",
    "AgentKitReadOnlyAccess",
)
ACTIONS = (
    "arkclaw:ListResources",
    "arkclaw:GetMpaInstanceConf",
    "apig:ListGateways",
    "apig:GetGateway",
    "apig:CreateGateway",
    "apig:CreateIMChannelGateway",
    "apig:GetIMChannelGatewayStatus",
    "apig:CreateUpstream",
    "apig:CreateRoute",
    "agentkit:DeleteSession",
    "agentkit:PauseSession",
    "agentkit:ResumeSession",
    "agentkit:SetSessionTtl",
    "agentkit:CreateSessionSnapshot",
)
POLICY_DOCUMENT = {
    "Statement": [{"Effect": "Allow", "Action": list(ACTIONS), "Resource": ["*"]}]
}
TRUST_DOCUMENT = {
    "Statement": [
        {
            "Effect": "Allow",
            "Action": ["sts:AssumeRole"],
            "Principal": {"Service": ["vefaas", "apig"]},
        }
    ]
}
ERROR_KEYS = frozenset(
    {
        "iamPermissionDenied",
        "iamTrustConflict",
        "iamPolicyConflict",
        "iamOwnershipConflict",
        "iamVerificationFailed",
        "iamConfigurationConflict",
    }
)
PERMISSION_CODES = {
    "AccessDenied",
    "Forbidden",
    "Unauthorized",
    "InvalidAccessKeyId",
    "SignatureDoesNotMatch",
    "InvalidToken",
    "ExpiredToken",
}
TRANSIENT_CODES = {
    "Throttling",
    "ThrottlingException",
    "TooManyRequests",
    "RequestLimitExceeded",
    "InternalError",
    "ServiceUnavailable",
    "InternalServerError",
    "RequestTimeout",
}
KNOWN_CODES = (
    PERMISSION_CODES
    | TRANSIENT_CODES
    | {
        "RoleNotExist",
        "PolicyNotExist",
        "RoleAlreadyExists",
        "PolicyAlreadyExist",
        "PolicyAttachConflict",
    }
)


class IamError(DeploymentError):
    """Only safe keys and recognized error codes survive the SDK boundary."""

    def __init__(self, code: str = "", *, key: str = "iamVerificationFailed"):
        self.code = code if code in KNOWN_CODES else ""
        self.key = (
            "iamPermissionDenied"
            if self.code in PERMISSION_CODES
            else (key if key in ERROR_KEYS else "iamVerificationFailed")
        )
        super().__init__(self.key)


class IamCloud:
    def __init__(self, runtime):
        self.runtime = runtime

    async def call(self, method: str, **params):
        def run():
            from volcengine.iam.IamService import IamService

            client = None
            try:
                credential = self.runtime._credentials()
                # IamService.__new__ is a singleton: bypass it to prevent concurrent
                # deployments from replacing each other's credentials/session.
                client = object.__new__(IamService)
                IamService.__init__(client)
                if getattr(self.runtime, "provider", "volcengine") == "byteplus":
                    from .provider import managed_host

                    client.set_host(
                        managed_host("iam", self.runtime.region, "byteplus")
                    )
                    client.service_info.credentials.region = self.runtime.region
                client.set_ak(credential.access_key_id)
                client.set_sk(credential.secret_access_key)
                client.set_session_token(credential.session_token)
                client.set_scheme("https")
                client.set_connection_timeout(5)
                client.set_socket_timeout(5)
                response = getattr(client, method)(params)
            except Exception as error:
                code = ""
                try:
                    envelope = json.loads(str(error))
                    code = (
                        envelope.get("ResponseMetadata", {})
                        .get("Error", {})
                        .get("Code", "")
                    )
                except (ValueError, AttributeError, TypeError):
                    pass
                if classify_error(error) == "permission":
                    code = "AccessDenied"
                raise IamError(code) from None
            finally:
                if client is not None and hasattr(client, "session"):
                    client.session.close()
            if not isinstance(response, dict):
                raise IamError()
            error = response.get("ResponseMetadata", {}).get("Error")
            if error:
                raise IamError(error.get("Code", ""))
            result = response.get("Result", {})
            if not isinstance(result, dict):
                raise IamError()
            return result

        return await asyncio.to_thread(run)


def _document(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def _canonical(value):
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, list):
        return sorted(
            (_canonical(item) for item in value),
            key=lambda item: json.dumps(item, sort_keys=True),
        )
    return value


def _validate_role(result: dict, account: str):
    role = result.get("Role", result)
    if (
        role.get("RoleName") != ROLE_NAME
        or role.get("Trn") != f"trn:iam::{account}:role/{ROLE_NAME}"
    ):
        raise IamError(key="iamOwnershipConflict")
    trust = _document(role.get("TrustPolicyDocument"))
    services = set()
    statements = trust.get("Statement", [])
    if not isinstance(statements, list):
        raise IamError(key="iamTrustConflict")
    for statement in statements:
        if not isinstance(statement, dict) or statement.get("Effect") == "Deny":
            raise IamError(key="iamTrustConflict")
        actions = statement.get("Action", [])
        principal = statement.get("Principal", {})
        if (
            statement.get("Effect") == "Allow"
            and not statement.get("Condition")
            and "sts:AssumeRole"
            in (actions if isinstance(actions, list) else [actions])
            and isinstance(principal, dict)
        ):
            service = principal.get("Service", [])
            if isinstance(service, str):
                service = [service]
            if isinstance(service, list) and all(
                isinstance(item, str) for item in service
            ):
                services.update(service)
    if not {"vefaas", "apig"} <= services:
        raise IamError(key="iamTrustConflict")


async def ensure_runtime_role(
    cloud, account: str, *, timeout: float = 120, poll_interval: float = 2
):
    """Reconcile by fixed names; never change existing trust/policy documents."""

    async def reconcile():
        deadline = time.monotonic() + timeout

        async def get_or_create(get, create, missing, collision, query, values):
            try:
                return await cloud.call(get, **query)
            except IamError as error:
                if error.code != missing:
                    raise
            try:
                await cloud.call(create, **values)
            except IamError as error:
                if error.code != collision:
                    raise
            return await cloud.call(get, **query)

        while True:
            try:
                role = await get_or_create(
                    "get_role",
                    "create_role",
                    "RoleNotExist",
                    "RoleAlreadyExists",
                    {"RoleName": ROLE_NAME},
                    {
                        "RoleName": ROLE_NAME,
                        "TrustPolicyDocument": json.dumps(TRUST_DOCUMENT),
                        "Description": "VeADK managed MPA execution role",
                    },
                )
                _validate_role(role, account)
                policy = await get_or_create(
                    "get_policy",
                    "create_policy",
                    "PolicyNotExist",
                    "PolicyAlreadyExist",
                    {"PolicyName": POLICY_NAME, "PolicyType": "Custom"},
                    {
                        "PolicyName": POLICY_NAME,
                        "PolicyDocument": json.dumps(POLICY_DOCUMENT),
                        "Description": "VeADK managed MPA runtime permissions v1",
                    },
                )
                if _canonical(
                    _document(policy.get("Policy", policy).get("PolicyDocument"))
                ) != _canonical(POLICY_DOCUMENT):
                    raise IamError(key="iamPolicyConflict")
                required = {(name, "System") for name in SYSTEM_POLICIES} | {
                    (POLICY_NAME, "Custom")
                }

                async def bindings():
                    result = await cloud.call(
                        "list_attached_role_policies", RoleName=ROLE_NAME
                    )
                    return {
                        (p.get("PolicyName"), p.get("PolicyType"))
                        for p in result.get("AttachedPolicyMetadata", [])
                        if any(
                            scope.get("PolicyScopeType") == "Global"
                            for scope in p.get("PolicyScope", [])
                        )
                    }

                attached = await bindings()
                for name, kind in sorted(required - attached):
                    try:
                        await cloud.call(
                            "attach_role_policy",
                            RoleName=ROLE_NAME,
                            PolicyName=name,
                            PolicyType=kind,
                        )
                    except IamError as error:
                        # A concurrent attachment still requires Global readback.
                        if error.code != "PolicyAttachConflict":
                            raise
                _validate_role(
                    await cloud.call("get_role", RoleName=ROLE_NAME), account
                )
                if required <= await bindings():
                    return
            except IamError as error:
                if error.code not in TRANSIENT_CODES | {
                    "RoleNotExist",
                    "PolicyNotExist",
                }:
                    raise
            if time.monotonic() >= deadline:
                raise IamError()
            await asyncio.sleep(poll_interval)

    try:
        await asyncio.wait_for(reconcile(), timeout)
    except asyncio.TimeoutError:
        raise IamError() from None
