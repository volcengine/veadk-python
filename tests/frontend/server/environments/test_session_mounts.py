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

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast

import pytest

from frontend.server.environments.service import EnvironmentService
from frontend.server.environments.session_mounts import (
    SessionEnvironmentMount,
    SessionEnvironmentMountRegistry,
    SessionEnvironmentSelection,
    SessionEnvironmentSelections,
)


@dataclass
class _ToolContext:
    environment_mount: object | None = None
    environment_mounts: object = ()


class _EnvironmentService:
    def __init__(
        self,
        *,
        base_environment: str = "aio-sandbox",
        phase: str = "available",
        tool_id: str = "tool-persisted",
        tool_status: str = "ready",
        provider: str = "volcengine",
        region: str = "cn-beijing",
    ) -> None:
        self.base_environment = base_environment
        self.phase = phase
        self.tool_id = tool_id
        self.tool_status = tool_status
        self.provider = provider
        self.region = region
        self.calls: list[tuple[str, str, str]] = []

    async def get(self, owner_id: str, environment_id: str) -> Any:
        raise AssertionError((owner_id, environment_id, "must not read mutable latest"))

    async def resolve_for_agent(
        self, owner_id: str, environment_id: str, version_id: str
    ) -> Any:
        raise AssertionError(
            (owner_id, environment_id, version_id, "must not provision during mount")
        )

    async def get_manifest(
        self, owner_id: str, environment_id: str, version_id: str
    ) -> Any:
        self.calls.append(("manifest", owner_id, environment_id))
        return SimpleNamespace(
            model_dump=lambda **kwargs: {
                "apiVersion": "agentkit.studio/v1alpha1",
                "kind": "Environment",
                "metadata": {
                    "id": environment_id,
                    "name": f"Environment {environment_id[:4]}",
                    "version": version_id,
                    "description": "Test environment",
                },
                "spec": {
                    "image": "registry.example/aio:test",
                    "baseEnvironment": self.base_environment,
                    "capabilities": ["shell", "cli"],
                },
                "status": {
                    "phase": self.phase,
                    "toolId": self.tool_id,
                    "toolStatus": self.tool_status,
                },
            }
        )

    def resource_info(self) -> dict[str, str]:
        return {"provider": self.provider, "region": self.region}


@pytest.mark.asyncio
async def test_resolve_returns_an_immutable_run_mount() -> None:
    service = _EnvironmentService()
    registry = SessionEnvironmentMountRegistry(cast(EnvironmentService, service))

    mount = await registry.resolve(
        "owner-1",
        SessionEnvironmentSelection(
            environment_id="a" * 32,
            environment_version_id="version-1",
            mount_instance_id=" mount-1 ",
        ),
    )

    assert mount.environment_id == "a" * 32
    assert mount.environment_version_id == "version-1"
    assert mount.mount_instance_id == "mount-1"
    assert mount.image == "registry.example/aio:test"
    assert mount.provider == "volcengine"
    assert mount.region == "cn-beijing"
    assert mount.name == "Environment aaaa"
    assert mount.description == "Test environment"
    assert mount.manifest["spec"]["capabilities"] == ["shell", "cli"]
    assert mount.tool_id == "tool-persisted"
    assert mount.tool_status == "ready"
    assert registry.get(_ToolContext(environment_mount=mount)) is mount


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "base_environment,provider,region",
    [
        ("aio-sandbox", "volcengine", "cn-beijing"),
        ("aio-sandbox", "byteplus", "ap-southeast-1"),
        ("codex-sandbox", "volcengine", "cn-beijing"),
        ("codex-sandbox", "byteplus", "ap-southeast-1"),
    ],
)
async def test_resolve_supports_sandbox_mounts_for_both_clouds(
    base_environment: str,
    provider: str,
    region: str,
) -> None:
    service = _EnvironmentService(
        base_environment=base_environment,
        provider=provider,
        region=region,
    )
    registry = SessionEnvironmentMountRegistry(cast(EnvironmentService, service))

    mount = await registry.resolve(
        "owner-1",
        SessionEnvironmentSelection(
            environment_id="a" * 32,
            environment_version_id="version-1",
        ),
    )

    assert mount.manifest["spec"]["baseEnvironment"] == base_environment
    assert mount.provider == provider
    assert mount.region == region


@pytest.mark.asyncio
async def test_resolve_requires_an_explicit_built_version() -> None:
    registry = SessionEnvironmentMountRegistry(
        cast(EnvironmentService, _EnvironmentService())
    )

    with pytest.raises(ValueError, match="必须指定已构建的环境版本"):
        await registry.resolve(
            "owner-1",
            SessionEnvironmentSelection(environment_id="a" * 32),
        )


@pytest.mark.asyncio
async def test_resolve_rejects_missing_persisted_tool_id() -> None:
    registry = SessionEnvironmentMountRegistry(
        cast(EnvironmentService, _EnvironmentService(tool_id=""))
    )

    with pytest.raises(ValueError, match="缺少已持久化的 Sandbox Tool"):
        await registry.resolve(
            "owner-1",
            SessionEnvironmentSelection(
                environment_id="a" * 32,
                environment_version_id="version-1",
            ),
        )


@pytest.mark.asyncio
async def test_resolve_rejects_non_ready_persisted_tool() -> None:
    registry = SessionEnvironmentMountRegistry(
        cast(
            EnvironmentService,
            _EnvironmentService(tool_id="tool-persisted", tool_status="creating"),
        )
    )

    with pytest.raises(ValueError, match=r"尚未 Ready（creating）"):
        await registry.resolve(
            "owner-1",
            SessionEnvironmentSelection(
                environment_id="a" * 32,
                environment_version_id="version-1",
            ),
        )


@pytest.mark.asyncio
async def test_resolve_many_preserves_order_and_rejects_unmounted_ids() -> None:
    service = _EnvironmentService()
    registry = SessionEnvironmentMountRegistry(cast(EnvironmentService, service))
    selections = SessionEnvironmentSelections.model_validate(
        [
            {"environment_id": "a" * 32, "environment_version_id": "version-1"},
            {"environment_id": "b" * 32, "environment_version_id": "version-1"},
        ]
    )

    mounts = await registry.resolve_many("owner-1", selections.root)
    context = _ToolContext(environment_mounts=mounts)

    assert [item.environment_id for item in mounts] == ["a" * 32, "b" * 32]
    assert registry.get(context, "b" * 32) is mounts[1]
    assert registry.get_all(context) == mounts
    with pytest.raises(ValueError, match="未挂载"):
        registry.get(context, "c" * 32)
    with pytest.raises(ValueError, match="必须指定"):
        registry.get(context)


def test_selection_list_rejects_duplicate_environment_ids() -> None:
    with pytest.raises(ValueError, match="重复"):
        SessionEnvironmentSelections.model_validate(
            [
                {"environment_id": "a" * 32},
                {"environment_id": "a" * 32},
            ]
        )


def test_selection_keeps_mount_instance_optional_for_legacy_clients() -> None:
    selection = SessionEnvironmentSelection(
        environment_id="a" * 32,
        environment_version_id="version-1",
    )

    assert selection.mount_instance_id == ""


def test_get_all_accepts_legacy_single_environment_mount() -> None:
    mount = SessionEnvironmentMount(
        environment_id="a" * 32,
        environment_version_id="version-1",
        image="registry.example/aio:test",
        provider="volcengine",
        region="cn-beijing",
        name="Legacy",
        description="",
        manifest={},
    )

    assert SessionEnvironmentMountRegistry.get_all(
        _ToolContext(environment_mount=mount)
    ) == (mount,)


@pytest.mark.asyncio
async def test_resolve_rejects_an_environment_without_sandbox_execution() -> None:
    registry = SessionEnvironmentMountRegistry(
        cast(EnvironmentService, _EnvironmentService(base_environment="ubuntu"))
    )

    with pytest.raises(ValueError, match="不支持 Sandbox 命令执行"):
        await registry.resolve(
            "owner-1",
            SessionEnvironmentSelection(
                environment_id="a" * 32,
                environment_version_id="version-1",
            ),
        )


def test_get_requires_a_mount_on_the_run_context() -> None:
    with pytest.raises(ValueError, match="尚未挂载"):
        SessionEnvironmentMountRegistry.get(_ToolContext())
