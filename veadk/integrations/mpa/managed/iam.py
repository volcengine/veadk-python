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
import hashlib
import json
import time

from .database import DeploymentError
from .diagnostics import (
    CATEGORIES,
    CODE_CATEGORIES,
    classify_error,
    exception_details,
    preserve_exception_details,
    report,
    safe_request_id,
)

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
        "iamTemporaryFailure",
        "iamConfigurationConflict",
        "tosBucketUnavailable",
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


TRANSIENT_CATEGORIES = {"timeout", "connection", "throttled", "unavailable"}
IAM_METHODS = {
    "get_role",
    "create_role",
    "get_policy",
    "create_policy",
    "attach_role_policy",
    "list_attached_role_policies",
}


class IamError(DeploymentError):
    """Retain safe request metadata while excluding provider messages and payloads."""

    def __init__(
        self,
        code: str = "",
        *,
        key: str = "iamVerificationFailed",
        category: str = "",
        operation: str = "",
        request_id: str = "",
    ):
        self.code = code if isinstance(code, str) and code in KNOWN_CODES else ""
        self.category = (
            "permission"
            if self.code in PERMISSION_CODES
            else CODE_CATEGORIES.get(
                self.code,
                category
                if isinstance(category, str) and category in CATEGORIES
                else "provider_error",
            )
        )
        self.operation = (
            "iam_" + operation if operation in IAM_METHODS else "iam_verify"
        )
        self.request_id = safe_request_id(request_id)
        self.key = (
            "iamPermissionDenied"
            if self.category == "permission"
            else "iamTemporaryFailure"
            if self.category in TRANSIENT_CATEGORIES
            else key
            if key in ERROR_KEYS
            else "iamVerificationFailed"
        )
        super().__init__(self.key)


def _metadata(value):
    if not isinstance(value, dict):
        return {}
    result = value.get("ResponseMetadata", {})
    return result if isinstance(result, dict) else {}


class IamCloud:
    def __init__(self, runtime):
        self.runtime = runtime

    async def verify_tos_bucket(self, bucket: str) -> None:
        """Only authorize a bucket owned by the verified deployment account."""

        def run():
            import tos

            client = None
            try:
                credential = self.runtime._credentials()
                client = tos.TosClientV2(
                    credential.access_key_id,
                    credential.secret_access_key,
                    f"https://tos-{self.runtime.region}.volces.com",
                    self.runtime.region,
                    security_token=credential.session_token,
                    connection_time=5,
                    socket_timeout=5,
                    max_retry_count=0,
                )
                if not any(
                    item.name == bucket and item.location == self.runtime.region
                    for item in (client.list_buckets().buckets or [])
                ):
                    raise IamError(key="tosBucketUnavailable")
            except IamError:
                raise
            except Exception as error:
                raise IamError(
                    "AccessDenied" if classify_error(error) == "permission" else ""
                ) from None
            finally:
                if client is not None:
                    client.close()

        await asyncio.to_thread(run)

    async def call(self, method: str, **params):
        if method not in IAM_METHODS:
            raise IamError(key="iamConfigurationConflict")

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
                metadata = {}
                try:
                    metadata = _metadata(json.loads(str(error)))
                except (ValueError, TypeError):
                    response = getattr(error, "response", None)
                    if response is not None:
                        try:
                            metadata = _metadata(response.json())
                        except (ValueError, TypeError, AttributeError):
                            pass
                category = classify_error(error)
                provider_error = metadata.get("Error", {})
                code = (
                    provider_error.get("Code", "")
                    if isinstance(provider_error, dict)
                    else ""
                )
                if category == "permission":
                    code = "AccessDenied"
                raise preserve_exception_details(
                    IamError(
                        code,
                        category=category,
                        operation=method,
                        request_id=metadata.get("RequestId", ""),
                    ),
                    error,
                ) from None
            finally:
                if client is not None and hasattr(client, "session"):
                    client.session.close()
            metadata = _metadata(response)
            error = metadata.get("Error")
            if error:
                raise IamError(
                    error.get("Code", "") if isinstance(error, dict) else "",
                    operation=method,
                    request_id=metadata.get("RequestId", ""),
                )
            result = response.get("Result", {}) if isinstance(response, dict) else None
            if not isinstance(result, dict):
                raise IamError(
                    category="protocol_error",
                    operation=method,
                    request_id=metadata.get("RequestId", ""),
                )
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


def _validate_role(
    result: dict,
    account: str,
    *,
    role_name: str = ROLE_NAME,
    required_services: tuple[str, ...] = ("vefaas", "apig"),
):
    role = result.get("Role", result)
    if (
        role.get("RoleName") != role_name
        or role.get("Trn") != f"trn:iam::{account}:role/{role_name}"
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
    if not set(required_services) <= services:
        raise IamError(key="iamTrustConflict")


async def ensure_tos_mount_permissions(
    cloud,
    account: str,
    bucket: str,
    *,
    role_name: str = ROLE_NAME,
    timeout: float = 120,
    poll_interval: float = 2,
):
    """Add one exact bucket policy without rewriting role or existing policies."""
    from .config import validate_tos_bucket_name

    bucket = validate_tos_bucket_name(bucket)
    if not bucket:
        raise IamError(key="iamConfigurationConflict")
    name = "VeADKMPATosMountV1_" + hashlib.sha256(bucket.encode()).hexdigest()[:20]
    document = {
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["tos:HeadBucket", "tos:ListBucket"],
                "Resource": [f"trn:tos:::{bucket}"],
            },
            {
                "Effect": "Allow",
                "Action": [
                    "tos:GetObject",
                    "tos:PutObject",
                    "tos:AbortMultipartUpload",
                    "tos:DeleteObject",
                ],
                "Resource": [f"trn:tos:::{bucket}/sandbox-session/*"],
            },
        ]
    }

    async def bindings():
        result = await cloud.call("list_attached_role_policies", RoleName=role_name)
        return any(
            item.get("PolicyName") == name
            and item.get("PolicyType") == "Custom"
            and any(
                scope.get("PolicyScopeType") == "Global"
                for scope in item.get("PolicyScope", [])
            )
            for item in result.get("AttachedPolicyMetadata", [])
        )

    async def reconcile():
        await cloud.verify_tos_bucket(bucket)
        deadline = time.monotonic() + timeout
        while True:
            try:
                _validate_role(
                    await cloud.call("get_role", RoleName=role_name),
                    account,
                    role_name=role_name,
                    required_services=("vefaas",),
                )
                query = {"PolicyName": name, "PolicyType": "Custom"}
                try:
                    policy = await cloud.call("get_policy", **query)
                except IamError as error:
                    if error.code != "PolicyNotExist":
                        raise
                    try:
                        await cloud.call(
                            "create_policy",
                            PolicyName=name,
                            PolicyDocument=json.dumps(document),
                            Description="MPA session output bucket access",
                        )
                    except IamError as error:
                        if error.code != "PolicyAlreadyExist":
                            raise
                    policy = await cloud.call("get_policy", **query)
                if _canonical(
                    _document(policy.get("Policy", policy).get("PolicyDocument"))
                ) != _canonical(document):
                    raise IamError(key="iamPolicyConflict")
                if not await bindings():
                    try:
                        await cloud.call(
                            "attach_role_policy", RoleName=role_name, **query
                        )
                    except IamError as error:
                        if error.code != "PolicyAttachConflict":
                            raise
                if await bindings():
                    _validate_role(
                        await cloud.call("get_role", RoleName=role_name),
                        account,
                        role_name=role_name,
                        required_services=("vefaas",),
                    )
                    return
            except IamError as error:
                if error.code not in TRANSIENT_CODES | {"PolicyNotExist"}:
                    raise
            if time.monotonic() >= deadline:
                raise IamError()
            await asyncio.sleep(poll_interval)

    try:
        await asyncio.wait_for(reconcile(), timeout)
    except asyncio.TimeoutError:
        raise IamError() from None


async def ensure_runtime_role(
    cloud, account: str, *, timeout: float = 120, poll_interval: float = 2
):
    """Reconcile by fixed names; never change existing trust/policy documents."""

    async def reconcile():
        deadline = time.monotonic() + timeout
        transient_attempt = 0

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
                if error.category in TRANSIENT_CATEGORIES:
                    transient_attempt += 1
                    retrying = transient_attempt < 4
                    report(
                        error.operation,
                        error.category,
                        attempt=transient_attempt,
                        outcome="retrying" if retrying else "failed",
                        request_id=error.request_id,
                        details=exception_details(error),
                    )
                    if not retrying:
                        raise
                    await asyncio.sleep(2 ** (transient_attempt - 1))
                    continue
                if error.code not in {"RoleNotExist", "PolicyNotExist"}:
                    report(
                        error.operation,
                        error.category,
                        request_id=error.request_id,
                        details=exception_details(error),
                    )
                    raise
            if time.monotonic() >= deadline:
                raise IamError(category="timeout")
            await asyncio.sleep(poll_interval)

    try:
        await asyncio.wait_for(reconcile(), timeout)
    except asyncio.TimeoutError:
        report("iam_verify", "timeout")
        raise IamError(category="timeout") from None
    except asyncio.CancelledError:
        report("iam_verify", "cancelled", outcome="cancelled")
        raise
