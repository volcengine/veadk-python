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

"""Read-only permission pre-check and guided authorization for Studio OTA."""

from __future__ import annotations

import fnmatch
import json
from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlencode

from veadk.cli.frontend_deploy_iam import DEFAULT_POLICY_NAME
from veadk.cli.studio_deploy_permissions import (
    AttachedPolicyDocument,
    PermissionSpec,
    PrincipalPolicySet,
    StudioDeployPermissionService,
    evaluate_actions,
)
from veadk.utils.cloud_provider import CloudProvider


def _permission(action: str, purpose_zh: str, purpose_en: str) -> PermissionSpec:
    return PermissionSpec(action, purpose_zh, purpose_en)


STUDIO_UPDATE_PERMISSION_SPECS: tuple[PermissionSpec, ...] = (
    _permission(
        "tos:GetObject", "读取并校验 Studio 更新包", "Read the Studio update bundle"
    ),
    _permission(
        "tos:ListBucket", "读取定时任务存储桶", "Read the scheduled-task bucket"
    ),
    _permission("tos:ListObjects", "列出定时任务数据", "List scheduled-task objects"),
    _permission(
        "vefaas:GetApplication",
        "查询 Studio 应用发布状态",
        "Check Studio release status",
    ),
    _permission(
        "vefaas:GetFunction",
        "读取 Studio 与调度函数配置",
        "Read Studio and scheduler Functions",
    ),
    _permission(
        "vefaas:ListFunctions", "查找定时任务调度函数", "Find scheduled-task Functions"
    ),
    _permission(
        "vefaas:CreateFunction",
        "创建缺失的定时任务调度函数",
        "Create missing scheduled-task Functions",
    ),
    _permission(
        "vefaas:GetCodeUploadAddress",
        "获取 Function 代码上传地址",
        "Get Function code upload addresses",
    ),
    _permission(
        "vefaas:CodeUploadCallback",
        "确认 Function 代码上传完成",
        "Confirm Function code uploads",
    ),
    _permission(
        "vefaas:UpdateFunction",
        "更新 Studio 与调度函数",
        "Update Studio and scheduler Functions",
    ),
    _permission(
        "vefaas:ReleaseApplication",
        "发布 Studio 应用新 Revision",
        "Release the new Studio revision",
    ),
    _permission(
        "vefaas:Release", "发布定时任务调度函数", "Release scheduled-task Functions"
    ),
    _permission(
        "vefaas:GetReleaseStatus",
        "查询调度函数发布状态",
        "Check scheduled-task Function releases",
    ),
    _permission(
        "vefaas:CreateDependencyInstallTask",
        "安装调度函数依赖",
        "Install scheduler Function dependencies",
    ),
    _permission(
        "vefaas:GetDependencyInstallTaskStatus",
        "查询依赖安装状态",
        "Check dependency installation status",
    ),
    _permission(
        "vefaas:GetDependencyInstallTaskLogDownloadURI",
        "读取依赖安装失败日志",
        "Read failed dependency installation logs",
    ),
    _permission(
        "vefaas:ListTriggers", "查找定时任务触发器", "Find scheduled-task triggers"
    ),
    _permission(
        "vefaas:CreateTimer", "创建定时任务触发器", "Create scheduled-task triggers"
    ),
    _permission(
        "vefaas:UpdateTimer", "更新定时任务触发器", "Update scheduled-task triggers"
    ),
)


_API_EXPLORER_HOSTS: dict[CloudProvider, str] = {
    "volcengine": "https://api.volcengine.com/api-explorer/",
    "byteplus": "https://api.byteplus.com/api-explorer/",
}

_IAM_CONSOLE_URLS: dict[CloudProvider, str] = {
    "volcengine": "https://console.volcengine.com/iam/policymanage",
    "byteplus": "https://console.byteplus.com/iam/policymanage",
}


@dataclass(frozen=True)
class StudioUpdatePermissionReport:
    """Permission decision returned before any OTA mutation starts."""

    ready: bool
    missing_actions: tuple[str, ...]
    policy_name: str
    authorization_url: str
    iam_console_url: str
    principal_name: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "missingActions": list(self.missing_actions),
            "policyName": self.policy_name,
            "authorizationUrl": self.authorization_url,
            "iamConsoleUrl": self.iam_console_url,
            "principalName": self.principal_name,
        }


class _PrincipalPolicyInspector(Protocol):
    """Minimal IAM inspection contract used by the OTA pre-check."""

    def principal_policies(self) -> PrincipalPolicySet: ...


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


def _has_explicit_deny(document: Mapping[str, Any], actions: Iterable[str]) -> bool:
    required = tuple(actions)
    for raw_statement in _as_list(document.get("Statement")):
        if not isinstance(raw_statement, Mapping):
            continue
        if str(raw_statement.get("Effect") or "").casefold() != "deny":
            continue
        if any(
            _matches_action(action, raw_statement.get("Action")) for action in required
        ):
            return True
    return False


def merge_policy_actions(
    document: Mapping[str, Any], actions: Iterable[str]
) -> dict[str, Any]:
    """Add required global Actions without replacing unrelated policy content."""
    merged = deepcopy(dict(document))
    statements = merged.get("Statement")
    if isinstance(statements, Mapping):
        statement_list: list[Any] = [dict(statements)]
    elif isinstance(statements, list):
        statement_list = deepcopy(statements)
    else:
        statement_list = []
    merged["Statement"] = statement_list

    missing = [
        action
        for action, satisfied in evaluate_actions(actions, [merged]).items()
        if not satisfied
    ]
    if not missing:
        return merged

    target: dict[str, Any] | None = None
    for raw_statement in statement_list:
        if not isinstance(raw_statement, dict):
            continue
        resources = _as_list(raw_statement.get("Resource", "*"))
        if (
            str(raw_statement.get("Effect") or "").casefold() == "allow"
            and not raw_statement.get("Condition")
            and resources
            and all(resource == "*" for resource in resources)
            and "Action" in raw_statement
        ):
            target = raw_statement
            break
    if target is None:
        target = {"Effect": "Allow", "Action": [], "Resource": ["*"]}
        statement_list.append(target)

    existing = [str(action) for action in _as_list(target.get("Action"))]
    target["Action"] = sorted(set(existing).union(missing), key=str.casefold)
    return merged


def build_update_policy_url(
    *, provider: CloudProvider, policy_name: str, policy_document: Mapping[str, Any]
) -> str:
    """Build an API Explorer link with the full UpdatePolicy form prefilled."""
    query = json.dumps(
        {
            "PolicyName": policy_name,
            "NewPolicyDocument": json.dumps(
                policy_document, ensure_ascii=False, separators=(",", ":")
            ),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    params = urlencode(
        {
            "action": "UpdatePolicy",
            "serviceCode": "iam",
            "version": "2018-01-01",
            "query": query,
        }
    )
    return f"{_API_EXPLORER_HOSTS[provider]}?{params}"


def _managed_policy(principal: PrincipalPolicySet) -> AttachedPolicyDocument | None:
    custom = [policy for policy in principal.policies if policy.policy_type == "Custom"]
    preferred = next(
        (policy for policy in custom if policy.name == DEFAULT_POLICY_NAME), None
    )
    if preferred is not None:
        return preferred
    return custom[0] if len(custom) == 1 else None


class StudioUpdatePermissionService:
    """Evaluate OTA permissions and prepare a user-confirmed policy update."""

    def __init__(
        self,
        *,
        provider: CloudProvider,
        access_key: str,
        secret_key: str,
        session_token: str = "",
        inspector: _PrincipalPolicyInspector | None = None,
    ) -> None:
        self.provider: CloudProvider = provider
        self.inspector = inspector or StudioDeployPermissionService(
            provider=provider,
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
        )

    def check(self) -> StudioUpdatePermissionReport:
        principal = self.inspector.principal_policies()
        if principal.kind == "root":
            return StudioUpdatePermissionReport(
                ready=True,
                missing_actions=(),
                policy_name="",
                authorization_url="",
                iam_console_url=_IAM_CONSOLE_URLS[self.provider],
                principal_name="",
            )
        evaluations = evaluate_actions(
            (spec.action for spec in STUDIO_UPDATE_PERMISSION_SPECS),
            (policy.document for policy in principal.policies),
        )
        missing = tuple(
            spec.action
            for spec in STUDIO_UPDATE_PERMISSION_SPECS
            if not evaluations.get(spec.action, False)
        )
        policy = _managed_policy(principal)
        authorization_url = ""
        policy_name = policy.name if policy is not None else ""
        has_explicit_deny = any(
            _has_explicit_deny(attached.document, missing)
            for attached in principal.policies
        )
        if missing and policy is not None and not has_explicit_deny:
            authorization_url = build_update_policy_url(
                provider=self.provider,
                policy_name=policy.name,
                policy_document=merge_policy_actions(policy.document, missing),
            )
        return StudioUpdatePermissionReport(
            ready=not missing,
            missing_actions=missing,
            policy_name=policy_name,
            authorization_url=authorization_url,
            iam_console_url=_IAM_CONSOLE_URLS[self.provider],
            principal_name=principal.name,
        )


__all__ = [
    "STUDIO_UPDATE_PERMISSION_SPECS",
    "StudioUpdatePermissionReport",
    "StudioUpdatePermissionService",
    "build_update_policy_url",
    "merge_policy_actions",
]
