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

"""Harness deploy integration, including opt-in Runtime VPC configuration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from importlib import import_module
from inspect import Parameter, signature
from pathlib import Path
from threading import RLock
from typing import Any

from agentkit.toolkit.harness.env_mapping import to_runtime_env as _base_to_runtime_env
from agentkit.toolkit.models import LifecycleResult
from agentkit.toolkit.reporter import Reporter

from .sidecar_config import sidecar_config_to_env


_core_deploy_module = import_module("agentkit.toolkit.harness.deploy")
_deploy_harness = _core_deploy_module.deploy_harness
_DEPLOY_COMPATIBILITY_LOCK = RLock()


def to_runtime_env(spec: dict[str, Any]) -> dict[str, str]:
    """Map a Harness spec without leaking Sidecar config into generic env keys."""

    sanitized = dict(spec)
    sidecar_section = sanitized.pop("sidecar", None)
    sidecar_profile = sanitized.get("profile")
    harness_section = sanitized.get("harness")
    if isinstance(harness_section, Mapping):
        if sidecar_section is None:
            sidecar_section = harness_section.get("sidecar")
        sidecar_profile = sidecar_profile or harness_section.get("profile")
        remaining_harness = dict(harness_section)
        remaining_harness.pop("sidecar", None)
        if remaining_harness:
            sanitized["harness"] = remaining_harness
        else:
            sanitized.pop("harness", None)

    env = _base_to_runtime_env(sanitized)
    if isinstance(sidecar_section, (Mapping, bool)):
        env.update(
            sidecar_config_to_env(
                sidecar_section,
                profile=str(sidecar_profile or "default"),
            )
        )
    return env


def build_runtime_network(
    *,
    mode: str | None = None,
    vpc_id: str | None = None,
    subnet_ids: list[str] | None = None,
    enable_shared_internet_access: bool | None = None,
) -> dict[str, Any]:
    """Build the cloud runner's Runtime network block when explicitly requested."""

    network: dict[str, Any] = {}
    if mode is not None:
        network["mode"] = mode
    if vpc_id is not None:
        network["vpc_id"] = vpc_id
    if subnet_ids:
        network["subnet_ids"] = subnet_ids
    if enable_shared_internet_access is not None:
        network["enable_shared_internet_access"] = enable_shared_internet_access
    return network


def _supports_extension_hooks(deploy: Callable[..., Any]) -> bool:
    """Return whether the installed SDK exposes the optional deploy hooks."""

    try:
        parameters = signature(deploy).parameters
    except (TypeError, ValueError):
        return False
    return "runtime_env_builder" in parameters or any(
        parameter.kind is Parameter.VAR_KEYWORD for parameter in parameters.values()
    )


def _deploy_with_legacy_sdk(
    *,
    name: str,
    path: str | Path,
    region: str | None,
    access_key: str | None,
    secret_key: str | None,
    discovery_url: str | None,
    allowed_id: str | None,
    cloud_overrides: dict[str, Any] | None,
    reporter: Reporter | None,
    on_conflict: Callable[[dict[str, Any]], bool] | None,
) -> LifecycleResult:
    """Scope Sidecar adapters around SDK 0.8.0/0.8.1 deploy execution.

    Those SDK releases resolve their environment/config builders from module
    globals and do not expose extension hooks. Deployment is synchronous, so a
    process-local lock plus ``finally`` restoration keeps this compatibility
    bridge isolated without replacing any files owned by the SDK distribution.
    """

    with _DEPLOY_COMPATIBILITY_LOCK:
        original_env_builder = _core_deploy_module.to_runtime_env
        original_config_builder = _core_deploy_module.build_agentkit_config

        def build_agentkit_config(*args: Any, **kwargs: Any) -> dict[str, Any]:
            config = original_config_builder(*args, **kwargs)
            if cloud_overrides:
                config["launch_types"]["cloud"].update(cloud_overrides)
            return config

        _core_deploy_module.to_runtime_env = to_runtime_env
        _core_deploy_module.build_agentkit_config = build_agentkit_config
        try:
            return _deploy_harness(
                name=name,
                path=path,
                region=region,
                access_key=access_key,
                secret_key=secret_key,
                discovery_url=discovery_url,
                allowed_id=allowed_id,
                reporter=reporter,
                on_conflict=on_conflict,
            )
        finally:
            _core_deploy_module.to_runtime_env = original_env_builder
            _core_deploy_module.build_agentkit_config = original_config_builder


def deploy_harness(
    name: str,
    path: str | Path = ".",
    *,
    region: str | None = None,
    access_key: str | None = None,
    secret_key: str | None = None,
    discovery_url: str | None = None,
    allowed_id: str | None = None,
    runtime_network_mode: str | None = None,
    runtime_vpc_id: str | None = None,
    runtime_subnet_ids: list[str] | None = None,
    runtime_enable_shared_internet_access: bool | None = None,
    reporter: Reporter | None = None,
    on_conflict: Callable[[dict[str, Any]], bool] | None = None,
) -> LifecycleResult:
    """Deploy a Sidecar-enabled Harness with optional Runtime networking."""

    runtime_network = build_runtime_network(
        mode=runtime_network_mode,
        vpc_id=runtime_vpc_id,
        subnet_ids=runtime_subnet_ids,
        enable_shared_internet_access=runtime_enable_shared_internet_access,
    )
    cloud_overrides = {"runtime_network": runtime_network} if runtime_network else None
    if _supports_extension_hooks(_deploy_harness):
        return _deploy_harness(
            name=name,
            path=path,
            region=region,
            access_key=access_key,
            secret_key=secret_key,
            discovery_url=discovery_url,
            allowed_id=allowed_id,
            runtime_env_builder=to_runtime_env,
            cloud_config_overrides=cloud_overrides,
            reporter=reporter,
            on_conflict=on_conflict,
        )
    return _deploy_with_legacy_sdk(
        name=name,
        path=path,
        region=region,
        access_key=access_key,
        secret_key=secret_key,
        discovery_url=discovery_url,
        allowed_id=allowed_id,
        cloud_overrides=cloud_overrides,
        reporter=reporter,
        on_conflict=on_conflict,
    )


__all__ = ["build_runtime_network", "deploy_harness", "to_runtime_env"]
