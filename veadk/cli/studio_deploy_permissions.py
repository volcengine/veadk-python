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

"""Read-only IAM pre-check for ``veadk studio deploy``."""

from __future__ import annotations

import fnmatch
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast
from urllib.parse import unquote

import click

from veadk.utils.cloud_provider import CloudProvider, iam_openapi_host

IAM_CONFIG_URLS: dict[CloudProvider, str] = {
    "volcengine": "https://console.volcengine.com/iam/policymanage",
    "byteplus": "https://console.byteplus.com/iam/policymanage",
}


@dataclass(frozen=True)
class PermissionSpec:
    """One IAM Action used by Studio deployment."""

    action: str
    purpose_zh: str
    purpose_en: str


@dataclass(frozen=True)
class PermissionResult:
    """Evaluated state for one required IAM Action."""

    spec: PermissionSpec
    satisfied: bool


def _permission(action: str, purpose_zh: str, purpose_en: str) -> PermissionSpec:
    return PermissionSpec(action, purpose_zh, purpose_en)


_IAM_PERMISSIONS = (
    _permission("iam:GetRole", "检查 Studio 所需的 IAM 角色", "Check Studio IAM roles"),
    _permission(
        "iam:GetPolicy", "检查 Studio 所需的 IAM 策略", "Check Studio IAM policies"
    ),
    _permission(
        "iam:CreatePolicy", "创建 Studio 所需的 IAM 策略", "Create Studio IAM policies"
    ),
    _permission(
        "iam:CreateRole", "创建 Studio 所需的 IAM 角色", "Create Studio IAM roles"
    ),
    _permission(
        "iam:ListAttachedRolePolicies",
        "检查 IAM 角色已绑定的策略",
        "List policies attached to Studio IAM roles",
    ),
    _permission(
        "iam:AttachRolePolicy",
        "为 Studio IAM 角色绑定策略",
        "Attach policies to Studio IAM roles",
    ),
)

_IDENTITY_PERMISSIONS = (
    _permission(
        "id:GetUserPool", "读取 Studio 身份用户池", "Read the Studio Identity user pool"
    ),
    _permission(
        "id:GetUserPoolClient",
        "读取 Studio 身份客户端",
        "Read the Studio Identity client",
    ),
    _permission(
        "id:UpdateUserPoolClient",
        "配置 Studio 登录回调地址",
        "Configure the Studio sign-in callback",
    ),
    _permission(
        "id:UpdateUserPool",
        "配置 Studio 用户池登录方式",
        "Configure Studio user-pool sign-in",
    ),
)

_AUTO_IDENTITY_PERMISSIONS = (
    _permission(
        "id:ListUserPools",
        "查找可复用的身份用户池",
        "Find a reusable Identity user pool",
    ),
    _permission(
        "id:CreateUserPool",
        "创建 Studio 身份用户池",
        "Create the Studio Identity user pool",
    ),
    _permission(
        "id:ListUserPoolClients",
        "查找可复用的身份客户端",
        "Find a reusable Identity client",
    ),
    _permission(
        "id:CreateUserPoolClient",
        "创建 Studio 身份客户端",
        "Create the Studio Identity client",
    ),
)

_STORAGE_PERMISSIONS = (
    _permission(
        "tos:ListBuckets", "查找 Studio 持久化存储桶", "Find the Studio storage bucket"
    ),
)

_SANDBOX_PERMISSIONS = (
    _permission(
        "agentkit:GetTool", "读取 Studio Sandbox Tool", "Read Studio Sandbox Tools"
    ),
    _permission(
        "agentkit:UpdateTool",
        "配置 Sandbox 模型凭据",
        "Configure Sandbox model credentials",
    ),
    _permission(
        "ark:ListApiKeys",
        "查找 Sandbox 使用的模型 API Key",
        "Find the model API key used by Sandbox",
    ),
    _permission(
        "ark:GetRawApiKey",
        "读取 Sandbox 使用的模型 API Key",
        "Read the model API key used by Sandbox",
    ),
)

_AUTO_SANDBOX_PERMISSIONS = (
    _permission(
        "agentkit:ListTools", "查找可复用的 Sandbox Tool", "Find reusable Sandbox Tools"
    ),
    _permission(
        "agentkit:CreateTool", "创建 Studio Sandbox Tool", "Create Studio Sandbox Tools"
    ),
)

_VEFAAS_PERMISSIONS = (
    _permission(
        "vefaas:CreateFunction",
        "创建 Studio VeFaaS 函数",
        "Create the Studio VeFaaS function",
    ),
    _permission(
        "vefaas:GetCodeUploadAddress",
        "获取 Studio 代码上传地址",
        "Get the Studio code upload address",
    ),
    _permission(
        "vefaas:CodeUploadCallback",
        "确认 Studio 代码上传完成",
        "Confirm the Studio code upload",
    ),
    _permission(
        "vefaas:CreateApplication",
        "创建 Studio VeFaaS 应用",
        "Create the Studio VeFaaS application",
    ),
    _permission(
        "vefaas:ReleaseApplication",
        "发布 Studio VeFaaS 应用",
        "Release the Studio VeFaaS application",
    ),
    _permission(
        "vefaas:GetApplication",
        "查询 Studio 应用发布状态",
        "Check the Studio application release status",
    ),
    _permission(
        "vefaas:GetApplicationRevisionLog",
        "读取失败的 Studio 应用发布日志",
        "Read failed Studio application release logs",
    ),
    _permission(
        "vefaas:UpdateFunction",
        "更新 Studio 函数环境变量",
        "Update Studio function environment variables",
    ),
    _permission(
        "vefaas:Release", "重新发布 Studio 函数", "Release the updated Studio function"
    ),
    _permission(
        "vefaas:GetReleaseStatus",
        "查询 Studio 函数发布状态",
        "Check the Studio function release status",
    ),
)


def required_permission_specs(
    *,
    auto_identity_resources: bool,
    auto_function_role: bool,
    auto_storage: bool,
    auto_sandbox_tools: bool,
    auto_gateway: bool,
    keep_failed_deploy: bool,
) -> list[PermissionSpec]:
    """Return the IAM Actions reachable for one Studio deploy invocation."""
    specs = list(_IAM_PERMISSIONS)
    if auto_function_role:
        specs.append(
            _permission(
                "iam:UpdatePolicy",
                "同步 Studio 函数角色策略",
                "Synchronize the Studio function-role policy",
            )
        )
    specs.extend(_IDENTITY_PERMISSIONS)
    if auto_identity_resources:
        specs.extend(_AUTO_IDENTITY_PERMISSIONS)
    if auto_storage:
        specs.append(
            _permission(
                "sts:GetCallerIdentity",
                "获取当前云账号以生成存储桶名称",
                "Resolve the current account for the storage bucket name",
            )
        )
    specs.extend(_STORAGE_PERMISSIONS)
    if auto_storage:
        specs.append(
            _permission(
                "tos:CreateBucket",
                "创建 Studio 持久化存储桶",
                "Create the Studio storage bucket",
            )
        )
    specs.extend(_SANDBOX_PERMISSIONS)
    if auto_sandbox_tools:
        specs.extend(_AUTO_SANDBOX_PERMISSIONS)
    if auto_gateway:
        specs.extend(
            (
                _permission(
                    "apig:ListGateways",
                    "查找可复用的 Serverless 网关",
                    "Find a reusable serverless gateway",
                ),
                _permission(
                    "apig:CreateGateway",
                    "创建 Serverless 网关",
                    "Create a serverless gateway",
                ),
            )
        )
    specs.append(
        _permission(
            "apig:UpdateRoute",
            "开放 Studio API 所需的 HTTP 方法",
            "Enable the HTTP methods required by Studio APIs",
        )
    )
    specs.extend(_VEFAAS_PERMISSIONS)
    if not keep_failed_deploy:
        specs.extend(
            (
                _permission(
                    "vefaas:DeleteApplication",
                    "清理创建失败的 Studio 应用",
                    "Clean up a failed Studio application",
                ),
                _permission(
                    "vefaas:DeleteFunction",
                    "清理创建失败的 Studio 函数",
                    "Clean up a failed Studio function",
                ),
            )
        )
    return specs


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value] if value is not None else []


def _matches_action(action: str, patterns: object) -> bool:
    normalized = action.casefold()
    return any(
        isinstance(pattern, str) and fnmatch.fnmatchcase(normalized, pattern.casefold())
        for pattern in _as_list(patterns)
    )


def _statement_matches_action(statement: Mapping[str, Any], action: str) -> bool:
    if "Action" in statement:
        return _matches_action(action, statement.get("Action"))
    if "NotAction" in statement:
        return not _matches_action(action, statement.get("NotAction"))
    return False


def _is_global_statement(statement: Mapping[str, Any]) -> bool:
    if statement.get("Condition"):
        return False
    resources = _as_list(statement.get("Resource", "*"))
    return bool(resources) and all(resource == "*" for resource in resources)


def _policy_document(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str):
        raise TypeError("IAM policy has no readable PolicyDocument")
    candidate = value.strip()
    for _ in range(2):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            decoded = unquote(candidate)
            if decoded == candidate:
                break
            candidate = decoded
            continue
        if isinstance(parsed, Mapping):
            return dict(parsed)
        break
    raise ValueError("IAM policy has no readable PolicyDocument")


def evaluate_actions(
    actions: Iterable[str], policy_documents: Iterable[object]
) -> dict[str, bool]:
    """Evaluate global Action statements; explicit Deny always wins."""
    documents = [_policy_document(document) for document in policy_documents]
    result: dict[str, bool] = {}
    for action in actions:
        allowed = False
        denied = False
        for document in documents:
            for raw_statement in _as_list(document.get("Statement")):
                if not isinstance(raw_statement, Mapping):
                    continue
                statement = cast(Mapping[str, Any], raw_statement)
                if not _is_global_statement(statement):
                    continue
                if not _statement_matches_action(statement, action):
                    continue
                effect = str(statement.get("Effect") or "").casefold()
                if effect == "deny":
                    denied = True
                elif effect == "allow":
                    allowed = True
        result[action] = allowed and not denied
    return result


def _iam_result(response: Mapping[str, Any]) -> dict[str, Any]:
    metadata = response.get("ResponseMetadata")
    if isinstance(metadata, Mapping) and metadata.get("Error"):
        error = metadata["Error"]
        if isinstance(error, Mapping):
            raise RuntimeError(str(error.get("Message") or error))
        raise RuntimeError(str(error))
    result = response.get("Result")
    return dict(result) if isinstance(result, Mapping) else {}


def _principal_name_from_trn(trn: str, kind: Literal["role", "user"]) -> str:
    prefixes = ("assumed-role", "role") if kind == "role" else ("user",)
    for prefix in prefixes:
        match = re.search(rf"(?:^|:|/){re.escape(prefix)}/([^/]+)", trn)
        if match:
            return match.group(1)
    return ""


class StudioDeployPermissionService:
    """Read the caller's attached IAM policies and evaluate deployment Actions."""

    def __init__(
        self,
        *,
        provider: CloudProvider,
        access_key: str,
        secret_key: str,
        session_token: str = "",
    ) -> None:
        self.provider: CloudProvider = provider
        self.access_key = access_key
        self.secret_key = secret_key
        self.session_token = session_token

    def _iam_service(self) -> Any:
        from volcengine.iam.IamService import IamService

        service = IamService()
        service.set_ak(self.access_key)
        service.set_sk(self.secret_key)
        service.set_host(iam_openapi_host(self.provider))
        service.set_scheme("https")
        service.set_connection_timeout(10)
        service.set_socket_timeout(10)
        if self.session_token:
            service.set_session_token(self.session_token)
        return service

    def _caller_identity(self) -> tuple[str, str]:
        from agentkit.platform.context import default_cloud_provider
        from agentkit.toolkit.volcengine.sts import VeSTS

        with default_cloud_provider(self.provider):
            identity = VeSTS(
                access_key=self.access_key,
                secret_key=self.secret_key,
                session_token=self.session_token,
            ).get_caller_identity()
        if identity is None:
            raise RuntimeError("IAM caller identity is unavailable")
        identity_type = str(identity.identity_type or "").casefold()
        trn = str(identity.trn or "")
        if "role" in identity_type:
            name = _principal_name_from_trn(trn, "role")
            if name:
                return "role", name
        if "user" in identity_type:
            name = _principal_name_from_trn(trn, "user")
            return "user", name
        if identity_type in {"account", "root", "primary"} or trn.endswith(":root"):
            return "root", ""
        raise RuntimeError("Could not resolve the current IAM role or user")

    def _user_name(self, service: Any) -> str:
        result = _iam_result(service.get_user({"AccessKeyID": self.access_key}))
        user = result.get("User", result)
        if isinstance(user, Mapping):
            return str(user.get("UserName") or "").strip()
        return ""

    def _attached_policy_documents(
        self, service: Any, principal_kind: str, principal_name: str
    ) -> list[dict[str, Any]]:
        if principal_kind == "role":
            response = service.list_attached_role_policies({"RoleName": principal_name})
        else:
            user_name = principal_name or self._user_name(service)
            if not user_name:
                raise RuntimeError("Could not resolve the current IAM user")
            response = service.list_attached_user_policies({"UserName": user_name})
        result = _iam_result(response)
        documents: list[dict[str, Any]] = []
        for policy in _as_list(result.get("AttachedPolicyMetadata", [])):
            if not isinstance(policy, Mapping):
                continue
            policy_name = str(policy.get("PolicyName") or "").strip()
            policy_type = str(policy.get("PolicyType") or "").strip()
            if not policy_name or policy_type not in {"System", "Custom"}:
                continue
            policy_result = _iam_result(
                service.get_policy(
                    {"PolicyName": policy_name, "PolicyType": policy_type}
                )
            )
            policy_data = policy_result.get("Policy", policy_result)
            if not isinstance(policy_data, Mapping):
                raise TypeError(f"IAM policy {policy_name} is unreadable")
            documents.append(_policy_document(policy_data.get("PolicyDocument")))
        return documents

    def check(self, specs: Iterable[PermissionSpec]) -> list[PermissionResult]:
        required = list(specs)
        principal_kind, principal_name = self._caller_identity()
        if principal_kind == "root":
            satisfied = {spec.action: True for spec in required}
        else:
            documents = self._attached_policy_documents(
                self._iam_service(), principal_kind, principal_name
            )
            satisfied = evaluate_actions((spec.action for spec in required), documents)
        return [
            PermissionResult(spec=spec, satisfied=satisfied.get(spec.action, False))
            for spec in required
        ]


def _table_lines(
    provider: CloudProvider, results: Iterable[PermissionResult]
) -> list[str]:
    rows = list(results)
    headers = (
        ("IAM Action", "Purpose", "Satisfied")
        if provider == "byteplus"
        else ("权限名称", "作用", "是否满足")
    )
    rendered = [
        (
            result.spec.action,
            result.spec.purpose_en
            if provider == "byteplus"
            else result.spec.purpose_zh,
            "✅" if result.satisfied else "❌",
        )
        for result in rows
    ]
    widths = [
        max(
            _terminal_width(headers[index]),
            *(_terminal_width(row[index]) for row in rendered),
        )
        for index in range(3)
    ]

    def line(row: tuple[str, str, str]) -> str:
        return (
            "| "
            + " | ".join(
                value + " " * (widths[index] - _terminal_width(value))
                for index, value in enumerate(row)
            )
            + " |"
        )

    separator = "|-" + "-|-".join("-" * width for width in widths) + "-|"
    return [line(headers), separator, *(line(row) for row in rendered)]


def _terminal_width(value: str) -> int:
    """Return the number of terminal columns occupied by plain table text."""
    width = 0
    for character in value:
        category = unicodedata.category(character)
        if category in {"Cf", "Mn", "Me"}:
            continue
        width += 2 if unicodedata.east_asian_width(character) in {"F", "W"} else 1
    return width


def render_permission_results(
    provider: CloudProvider, results: Iterable[PermissionResult]
) -> None:
    """Print every required Action and its evaluated state."""
    rows = list(results)
    missing = [result for result in rows if not result.satisfied]
    click.echo("")
    click.echo(
        "Studio deployment IAM pre-check"
        if provider == "byteplus"
        else "Studio 部署 IAM 权限预检"
    )
    for line in _table_lines(provider, rows):
        click.echo(line)
    click.echo("")
    if provider == "byteplus":
        if missing:
            click.echo(f"Missing {len(missing)} of {len(rows)} required IAM Actions.")
        else:
            click.echo(f"All {len(rows)} required IAM Actions are satisfied.")
        click.echo(
            f"Configure permissions in BytePlus IAM: {IAM_CONFIG_URLS[provider]}"
        )
    else:
        if missing:
            click.echo(f"共 {len(rows)} 项 IAM 权限，缺少 {len(missing)} 项。")
        else:
            click.echo(f"共 {len(rows)} 项 IAM 权限，已全部满足。")
        click.echo(f"前往火山引擎 IAM 配置权限：{IAM_CONFIG_URLS[provider]}")


def run_studio_deploy_permission_precheck(
    *,
    provider: CloudProvider,
    access_key: str,
    secret_key: str,
    session_token: str,
    specs: Iterable[PermissionSpec],
) -> list[PermissionResult]:
    """Evaluate and render the Studio deployment permission table."""
    results = StudioDeployPermissionService(
        provider=provider,
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
    ).check(specs)
    render_permission_results(provider, results)
    return results


__all__ = [
    "IAM_CONFIG_URLS",
    "PermissionResult",
    "PermissionSpec",
    "StudioDeployPermissionService",
    "evaluate_actions",
    "render_permission_results",
    "required_permission_specs",
    "run_studio_deploy_permission_precheck",
]
