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

"""Public VeADK adapter for AgentKit Harness Sidecar product selections."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any, Literal, cast

logger = logging.getLogger(__name__)

STUDIO_HARNESS_COMPONENT_IDS = (
    "context_engine",
    "compressor",
    "verifier",
    "long_run_control",
    "mcp_resilience",
)
STUDIO_HARNESS_PROFILE_DEFAULTS = {
    "default": (
        "context_engine",
        "compressor",
        "verifier",
        "long_run_control",
    ),
    "ops": STUDIO_HARNESS_COMPONENT_IDS,
}
_STUDIO_HARNESS_PROFILE_METADATA = {
    "default": (
        "通用增强",
        "适用于通用对话、知识问答和常规 Agent 的默认增强能力。",
    ),
    "ops": (
        "运维增强",
        "面向运维诊断、数据库、日志和监控 MCP 的安全增强能力。",
    ),
}
STUDIO_HARNESS_CATALOG_VERSION = "2026.07.1"
_STUDIO_HARNESS_OPTIONS = {
    "context_engine": (
        "上下文治理",
        "治理上下文组装、任务锚定和上下文预算。",
    ),
    "compressor": (
        "上下文与结果压缩",
        "压缩长上下文和大型工具结果，降低 Token 成本。",
    ),
    "verifier": (
        "回答校验与修复",
        "校验证据和回答，在失败时执行修复或告警。",
    ),
    "long_run_control": (
        "Goal任务控制",
        "管理 Goal 任务的进度、续跑和结束条件。",
    ),
    "mcp_resilience": (
        "MCP 稳定性治理",
        "治理连接、超时、空结果、大返回和调用预算；默认包含 SQL 只读保护。",
    ),
}
_HIDDEN_COMPONENT_ID = "sql_readonly"
_INCOMPATIBLE_IMAGE_MESSAGE = (
    "The Runtime image is incompatible with managed Harness Sidecar support. "
    "Use a Sidecar-enabled managed Runtime image."
)
_AGENTKIT_CLI_ENV = "VEADK_AGENTKIT_CLI"


class HarnessSidecarDependencyError(RuntimeError):
    """Raised when managed Sidecar support is unavailable or incompatible."""


@dataclass(frozen=True)
class StudioHarnessIntent:
    """Normalized Studio-owned intent containing only user-selectable options."""

    enabled: bool
    profile: str
    component_overrides: dict[str, bool]
    catalog_version: str | None = None
    plan_hash: str | None = None


def _sidecar_runtime_api() -> Any:
    """Load VeADK's in-tree Python Runtime lifecycle integration."""

    from veadk.extensions.harness import sidecar_runtime

    return sidecar_runtime


def agentkit_cli_executable() -> str:
    """Resolve the configured AgentKit CLI without invoking a shell."""

    configured = os.getenv(_AGENTKIT_CLI_ENV, "agentkit").strip()
    executable = shutil.which(configured)
    if executable is None:
        raise HarnessSidecarDependencyError(
            "AgentKit CLI is required for managed Harness Sidecar operations."
        )
    return executable


def _run_agentkit_cli_json(arguments: list[str]) -> dict[str, Any]:
    """Run one bounded, read-only AgentKit CLI control-plane command."""

    try:
        result = subprocess.run(
            [agentkit_cli_executable(), *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HarnessSidecarDependencyError(
            "AgentKit CLI Harness Sidecar control plane is unavailable."
        ) from error
    try:
        payload = json.loads(result.stdout)
    except (TypeError, ValueError) as error:
        raise HarnessSidecarDependencyError(
            "AgentKit CLI returned an invalid Harness Sidecar response."
        ) from error
    if not isinstance(payload, dict):
        raise HarnessSidecarDependencyError(
            "AgentKit CLI returned an invalid Harness Sidecar response."
        )
    if result.returncode not in {0, 1}:
        raise HarnessSidecarDependencyError(
            "AgentKit CLI failed to resolve the Harness Sidecar request."
        )
    return payload


def normalize_studio_harness_intent(value: Any | None) -> StudioHarnessIntent:
    """Validate Studio profile/options and derive ``enabled`` from checkboxes."""

    if value is None:
        raw: dict[str, Any] = {}
    elif isinstance(value, StudioHarnessIntent):
        return value
    elif isinstance(value, Mapping):
        raw = dict(value)
    else:
        model_dump = getattr(value, "model_dump", None)
        if not callable(model_dump):
            raise TypeError("harnessSidecar must be an object")
        dumped = model_dump(mode="python", by_alias=True)
        if not isinstance(dumped, Mapping):
            raise TypeError("harnessSidecar must serialize to an object")
        raw = dict(cast(Mapping[str, Any], dumped))

    profile = str(raw.get("profile") or "default")
    if profile not in STUDIO_HARNESS_PROFILE_DEFAULTS:
        supported = ", ".join(STUDIO_HARNESS_PROFILE_DEFAULTS)
        raise ValueError(f"Studio Harness Sidecar profile must be one of: {supported}")
    raw_overrides = raw.get("componentOverrides", raw.get("component_overrides", {}))
    if raw_overrides is None:
        raw_overrides = {}
    if not isinstance(raw_overrides, Mapping):
        raise ValueError("Harness Sidecar componentOverrides must be an object")
    unknown = sorted(set(raw_overrides) - set(STUDIO_HARNESS_COMPONENT_IDS))
    if unknown:
        raise ValueError(
            "Unknown or non-selectable Studio Harness option: " + ", ".join(unknown)
        )
    invalid = sorted(
        component_id
        for component_id, selected in raw_overrides.items()
        if not isinstance(selected, bool)
    )
    if invalid:
        raise ValueError(
            "Studio Harness option values must be boolean: " + ", ".join(invalid)
        )
    overrides = {
        component_id: bool(raw_overrides.get(component_id, False))
        for component_id in STUDIO_HARNESS_COMPONENT_IDS
    }
    return StudioHarnessIntent(
        enabled=any(overrides.values()),
        profile=profile,
        component_overrides=overrides,
        catalog_version=_optional_string(
            raw.get("catalogVersion", raw.get("catalog_version"))
        ),
        plan_hash=_optional_string(raw.get("planHash", raw.get("plan_hash"))),
    )


def studio_harness_intent_payload(value: Any | None) -> dict[str, Any]:
    """Return the stable camelCase Draft/YAML representation."""

    intent = normalize_studio_harness_intent(value)
    payload: dict[str, Any] = {
        "enabled": intent.enabled,
        "profile": intent.profile,
        "componentOverrides": dict(intent.component_overrides),
    }
    if intent.catalog_version:
        payload["catalogVersion"] = intent.catalog_version
    if intent.plan_hash:
        payload["planHash"] = intent.plan_hash
    return payload


def get_studio_harness_sidecar_catalog() -> dict[str, Any]:
    """Return this VeADK release's fixed Studio option metadata without I/O."""

    components = [
        {
            "id": component_id,
            "displayName": _STUDIO_HARNESS_OPTIONS[component_id][0],
            "description": _STUDIO_HARNESS_OPTIONS[component_id][1],
            "selectable": True,
            "dependencies": [],
            "riskLevel": "standard",
            "status": "ga",
            "availability": {
                "available": True,
                "status": "integrated",
                "reason": None,
                "minRuntimeVersion": None,
                "regions": [],
            },
        }
        for component_id in STUDIO_HARNESS_COMPONENT_IDS
    ]
    return {
        "schemaVersion": "veadk.studio.harness-sidecar.catalog/v1",
        "catalogVersion": STUDIO_HARNESS_CATALOG_VERSION,
        "profile": "default",
        "profiles": [
            {
                "id": profile_id,
                "displayName": _STUDIO_HARNESS_PROFILE_METADATA[profile_id][0],
                "description": _STUDIO_HARNESS_PROFILE_METADATA[profile_id][1],
                "defaultComponents": list(default_components),
                "autoAddedComponents": (
                    [_HIDDEN_COMPONENT_ID] if profile_id == "ops" else []
                ),
            }
            for profile_id, default_components in STUDIO_HARNESS_PROFILE_DEFAULTS.items()
        ],
        "components": components,
    }


def resolve_studio_harness_sidecar_selection(value: Any | None) -> dict[str, Any]:
    """Resolve one Studio intent while keeping SQL readonly server-owned."""

    intent, plan = _resolve_agentkit_plan(value)
    return _studio_plan_payload(intent, plan)


def studio_harness_deployment_config(
    value: Any | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the public AgentKit CLI selection contract for deployment."""

    intent, plan = _resolve_agentkit_plan(value)
    studio_plan = _studio_plan_payload(intent, plan)
    if not intent.enabled:
        return {}, studio_plan
    if not plan.get("valid", False):
        raise ValueError("; ".join(plan.get("errors") or []))
    if intent.plan_hash and intent.plan_hash != plan.get("plan_hash"):
        raise ValueError("Harness Sidecar plan has changed; resolve it again")
    return (
        {
            "enabled": True,
            "profile": intent.profile,
            "catalog_version": plan.get("catalog_version"),
            "component_overrides": dict(intent.component_overrides),
        },
        studio_plan,
    )


def _studio_plan_payload(
    intent: StudioHarnessIntent,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    requested = [
        component_id
        for component_id in STUDIO_HARNESS_COMPONENT_IDS
        if intent.enabled and intent.component_overrides[component_id]
    ]
    effective = list(plan.get("effective_components") or [])
    auto_added = [
        {
            "id": item.get("id"),
            "requiredBy": list(item.get("required_by") or []),
        }
        for item in plan.get("auto_added_components") or []
        if item.get("id") not in requested
    ]
    if _HIDDEN_COMPONENT_ID in effective:
        auto_added = [item for item in auto_added if item["id"] != _HIDDEN_COMPONENT_ID]
        auto_added.append(
            {
                "id": _HIDDEN_COMPONENT_ID,
                "requiredBy": ["mcp_resilience"],
            }
        )
    return {
        "schemaVersion": "veadk.studio.harness-sidecar.plan/v1",
        "valid": bool(plan.get("valid", False)),
        "enabled": intent.enabled,
        "profile": intent.profile,
        "componentOverrides": dict(intent.component_overrides),
        "requestedComponents": requested,
        "effectiveComponents": effective,
        "autoAddedComponents": auto_added,
        "warnings": list(plan.get("warnings") or []),
        "errors": list(plan.get("errors") or []),
        "catalogVersion": plan.get("catalog_version"),
        "planHash": plan.get("plan_hash"),
    }


def studio_harness_runtime_env(
    value: Any | None,
    *,
    transport: Literal["local", "apig_runtime_port"],
) -> tuple[dict[str, str], dict[str, Any]]:
    """Build public Runtime env for the exact plan selected in Studio."""

    intent, plan = _resolve_agentkit_plan(value)
    if not intent.enabled:
        return {}, _studio_plan_payload(intent, plan)
    if not plan.get("valid", False):
        raise ValueError("; ".join(plan.get("errors") or []))
    activation_targets = dict(plan.get("activation_targets") or {})
    model_proxy = dict(activation_targets.get("model_proxy") or {})
    mcp_gateway = dict(activation_targets.get("mcp_gateway") or {})
    runtime_overrides = _runtime_component_overrides(intent)
    model_components = list(model_proxy.get("components") or [])
    mcp_enabled = bool(mcp_gateway.get("enabled", False))
    config: dict[str, Any] = {
        "enabled": True,
        "profile": intent.profile,
        "catalog_version": plan.get("catalog_version"),
        "component_overrides": runtime_overrides,
        "fail_open": False,
        "transport": transport,
        "model_proxy": {
            "enabled": True,
            "components": model_components,
            "fail_open": False,
        },
        "mcp_gateway": {
            "enabled": mcp_enabled,
            "fail_open": False,
        },
    }
    if transport == "apig_runtime_port":
        config["model_proxy"].update(
            {
                "host": "0.0.0.0",
                "port": 18787,
                "prefer_configured_upstream_api_key": True,
            }
        )
        config["mcp_gateway"].update(
            {
                "host": "0.0.0.0",
                "port": 18788 if mcp_enabled else 0,
                "prefer_configured_upstream_api_key": mcp_enabled,
            }
        )
    env = _sidecar_runtime_api().sidecar_config_to_env(
        config,
        profile=intent.profile,
    )
    env["HARNESS_SIDECAR_EXPECTED_PLAN_HASH"] = str(plan.get("plan_hash") or "")
    return env, _studio_plan_payload(intent, plan)


def studio_harness_env_example(value: Any | None) -> dict[str, str]:
    """Return only public, portable selection values for ``.env.example``."""

    intent = normalize_studio_harness_intent(value)
    if not intent.enabled:
        return {}
    import json

    return {
        "HARNESS_SIDECAR_ENABLED": "true",
        "HARNESS_SIDECAR_FAIL_OPEN": "false",
        "HARNESS_PROFILE": intent.profile,
        "HARNESS_SIDECAR_CATALOG_VERSION": STUDIO_HARNESS_CATALOG_VERSION,
        "HARNESS_SIDECAR_COMPONENT_OVERRIDES": json.dumps(
            _runtime_component_overrides(intent),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    }


def _resolve_agentkit_plan(
    value: Any | None,
) -> tuple[StudioHarnessIntent, dict[str, Any]]:
    intent = normalize_studio_harness_intent(value)
    if not intent.enabled:
        return intent, _disabled_agentkit_plan(intent)
    arguments = [
        "harness",
        "sidecar",
        "resolve",
        "--profile",
        intent.profile,
    ]
    if intent.catalog_version:
        arguments.extend(["--catalog-version", intent.catalog_version])
    for component_id in STUDIO_HARNESS_COMPONENT_IDS:
        selected = str(intent.component_overrides[component_id]).lower()
        arguments.extend(["--component", f"{component_id}={selected}"])
    plan = _run_agentkit_cli_json(arguments)
    if not isinstance(plan, Mapping):
        raise HarnessSidecarDependencyError(
            "AgentKit CLI returned an invalid Harness Sidecar response."
        )
    return intent, dict(plan)


def _disabled_agentkit_plan(intent: StudioHarnessIntent) -> dict[str, Any]:
    """Return the ordinary-runtime plan without loading the Sidecar control plane."""

    return {
        "schema_version": "agentkit.harness-sidecar.plan/v1",
        "valid": True,
        "enabled": False,
        "profile": intent.profile,
        "requested_components": [],
        "effective_components": [],
        "auto_added_components": [],
        "activation_targets": {
            "veadk_plugins": [],
            "model_proxy": {"enabled": False, "components": []},
            "mcp_gateway": {
                "enabled": False,
                "presets": [],
                "readonly_segments": [],
            },
            "runtime_components": [],
        },
        "warnings": [],
        "errors": [],
        "catalog_version": intent.catalog_version or "",
        "runtime_version": None,
        "plan_hash": "",
    }


def _runtime_component_overrides(intent: StudioHarnessIntent) -> dict[str, bool]:
    return {
        **intent.component_overrides,
        _HIDDEN_COMPONENT_ID: intent.component_overrides["mcp_resilience"],
    }


class ManagedHarnessSidecar:
    """Own one Sidecar binding without exposing process details to VeADK users."""

    def __init__(
        self,
        config: bool | Mapping[str, Any] | Any = False,
        *,
        profile: str = "default",
        process_env: Mapping[str, str] | None = None,
        binding_env: MutableMapping[str, str] | None = None,
    ) -> None:
        self.config = config
        self.profile = profile
        self.process_env = process_env
        self.binding_env = binding_env if binding_env is not None else os.environ
        self.binding: Any | None = None
        self.error: Exception | None = None
        self._attempted = False
        self.plan = resolve_sidecar_plan(config, profile=profile)

    @property
    def enabled(self) -> bool:
        if isinstance(self.config, bool):
            return self.config
        if isinstance(self.config, Mapping):
            return bool(self.config.get("enabled", True))
        return bool(getattr(self.config, "enabled", True))

    @property
    def fail_open(self) -> bool:
        if isinstance(self.config, Mapping):
            return bool(self.config.get("fail_open", True))
        return bool(getattr(self.config, "fail_open", True))

    @property
    def status(self) -> str:
        if self.binding is not None:
            return str(self.binding.spec.status)
        if self.error is not None:
            return "degraded"
        return "not_started" if self.enabled else "disabled"

    @property
    def env(self) -> dict[str, str]:
        return dict(self.binding.env) if self.binding is not None else {}

    @property
    def plan_hash(self) -> str | None:
        if self.binding is not None:
            return getattr(self.binding.spec, "plan_hash", None)
        return getattr(self.plan, "plan_hash", None)

    def start(self) -> Any | None:
        if not self.enabled or self.binding is not None or self._attempted:
            return self.binding
        self._attempted = True
        try:
            self.binding = _public_start_function()(
                self.config,
                profile=self.profile,
                apply_env=True,
                environ=self.binding_env,
                process_env=self.process_env,
            )
        except Exception as error:
            self.error = error
            if not self.fail_open:
                raise
            logger.warning("Harness Sidecar startup failed open: %s", error)
        return self.binding

    def close(self) -> None:
        if self.binding is not None:
            self.binding.stop()
            self.binding = None


def sidecar_config_from_env(env: Mapping[str, str] | None = None) -> Any | bool:
    """Load the public AgentKit Sidecar config only when explicitly enabled."""

    values = env if env is not None else os.environ
    if not _truthy(values.get("HARNESS_SIDECAR_ENABLED")):
        return False
    try:
        return _sidecar_runtime_api().HarnessSidecarConfig.from_env(values)
    except AttributeError as error:
        raise HarnessSidecarDependencyError(_INCOMPATIBLE_IMAGE_MESSAGE) from error


def normalize_sidecar_config(value: Any | None) -> bool | dict[str, Any]:
    """Convert public config objects into VeADK's serializable extension config."""

    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if not isinstance(dumped, Mapping):
            raise TypeError("sidecar config must serialize to an object")
        return dict(cast(Mapping[str, Any], dumped))
    raise TypeError("sidecar must be a bool, mapping, or HarnessSidecarConfig")


def resolve_sidecar_plan(
    value: bool | Mapping[str, Any] | Any,
    *,
    profile: str,
) -> Any | None:
    """Resolve the public Product Component plan without starting the Runtime."""

    enabled = (
        value
        if isinstance(value, bool)
        else bool(
            value.get("enabled", True)
            if isinstance(value, Mapping)
            else getattr(value, "enabled", True)
        )
    )
    if not enabled:
        return None
    try:
        config = _sidecar_runtime_api().resolve_sidecar_config(value, profile=profile)
    except AttributeError as error:
        raise HarnessSidecarDependencyError(_INCOMPATIBLE_IMAGE_MESSAGE) from error
    plan = config.resolved_plan
    if not plan.valid:
        raise ValueError("; ".join(plan.errors))
    return plan


def _public_start_function() -> Any:
    try:
        return _sidecar_runtime_api().start_harness_sidecar
    except AttributeError as error:
        raise HarnessSidecarDependencyError(_INCOMPATIBLE_IMAGE_MESSAGE) from error


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _truthy(value: str | None) -> bool:
    return bool(value and value.strip().lower() in {"1", "true", "yes", "on"})


__all__ = [
    "STUDIO_HARNESS_COMPONENT_IDS",
    "HarnessSidecarDependencyError",
    "ManagedHarnessSidecar",
    "StudioHarnessIntent",
    "agentkit_cli_executable",
    "get_studio_harness_sidecar_catalog",
    "normalize_sidecar_config",
    "normalize_studio_harness_intent",
    "resolve_sidecar_plan",
    "resolve_studio_harness_sidecar_selection",
    "sidecar_config_from_env",
    "studio_harness_env_example",
    "studio_harness_intent_payload",
    "studio_harness_runtime_env",
]
