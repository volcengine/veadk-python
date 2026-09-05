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

"""Resolve Studio environment selections into immutable per-run mounts."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

from .service import EnvironmentService


class SessionEnvironmentSelection(BaseModel):
    """Studio-only environment fields removed before forwarding to Runtime."""

    model_config = ConfigDict(extra="forbid")

    environment_id: str = Field(min_length=32, max_length=32)
    environment_version_id: str = Field(default="", max_length=128)
    mount_instance_id: str = Field(default="", max_length=128)


class SessionEnvironmentSelections(RootModel[list[SessionEnvironmentSelection]]):
    """Validated ordered whitelist of environments mounted to one session."""

    root: list[SessionEnvironmentSelection] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def reject_duplicate_environment_ids(self) -> SessionEnvironmentSelections:
        environment_ids = [item.environment_id for item in self.root]
        if len(set(environment_ids)) != len(environment_ids):
            raise ValueError("会话环境不能包含重复项。")
        return self


@dataclass(frozen=True)
class SessionEnvironmentMount:
    """Validated image and cloud metadata available to one Agent run."""

    environment_id: str
    environment_version_id: str
    image: str
    provider: str
    region: str
    name: str = ""
    description: str = ""
    manifest: Mapping[str, Any] = field(default_factory=dict)
    tool_id: str = ""
    tool_status: str = ""
    mount_instance_id: str = ""


class _StudioToolContext(Protocol):
    @property
    def environment_mount(self) -> object | None: ...

    @property
    def environment_mounts(self) -> object: ...


class SessionEnvironmentMountRegistry:
    """Resolve a session selection and read the immutable run-scoped result.

    The frontend owns the session-level choice and includes it on every
    ``run_sse`` request. The BFF resolves that choice once and places the
    immutable result on ``StudioToolExecutionContext``. Keeping the mount on
    the run context avoids cross-session state and works across BFF instances.
    """

    def __init__(self, environment_service: EnvironmentService) -> None:
        self._environment_service = environment_service

    async def resolve(
        self,
        owner_id: str,
        selection: SessionEnvironmentSelection,
    ) -> SessionEnvironmentMount:
        version_id = selection.environment_version_id.strip()
        if not version_id:
            raise ValueError("挂载环境时必须指定已构建的环境版本。")
        manifest_model = await self._environment_service.get_manifest(
            owner_id,
            selection.environment_id,
            version_id,
        )
        manifest = manifest_model.model_dump(mode="json", by_alias=True)
        metadata = manifest.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        spec = manifest.get("spec")
        if not isinstance(spec, dict):
            raise TypeError("环境 Manifest 缺少 spec。")
        if spec.get("baseEnvironment") not in {"aio-sandbox", "codex-sandbox"}:
            raise ValueError("所选环境不支持 Sandbox 命令执行。")
        image = _string_value(spec.get("image"))
        if not image:
            raise ValueError("所选环境版本缺少镜像。")
        status = manifest.get("status")
        if not isinstance(status, dict):
            raise TypeError("环境 Manifest 缺少 status。")
        if status.get("phase") != "available":
            raise ValueError("所选环境版本尚未构建完成。")
        tool_id = _string_value(status.get("toolId"))
        tool_status = _string_value(status.get("toolStatus")).lower()
        if not tool_id:
            raise ValueError(
                "所选环境版本缺少已持久化的 Sandbox Tool，请重新构建环境。"
            )
        if tool_status != "ready":
            detail = tool_status or "unknown"
            raise ValueError(f"所选环境版本的 Sandbox Tool 尚未 Ready（{detail}）。")
        provider, region = _resource_location(self._environment_service.resource_info())
        return SessionEnvironmentMount(
            environment_id=selection.environment_id,
            environment_version_id=version_id,
            image=image,
            provider=provider,
            region=region,
            name=_string_value(metadata.get("name")) or selection.environment_id,
            description=_string_value(metadata.get("description")),
            manifest=manifest,
            tool_id=tool_id,
            tool_status=tool_status,
            mount_instance_id=selection.mount_instance_id.strip(),
        )

    async def resolve_many(
        self,
        owner_id: str,
        selections: Sequence[SessionEnvironmentSelection],
    ) -> tuple[SessionEnvironmentMount, ...]:
        """Resolve an ordered session whitelist into immutable mounts."""

        environment_ids = [item.environment_id for item in selections]
        if len(set(environment_ids)) != len(environment_ids):
            raise ValueError("会话环境不能包含重复项。")
        mounts = await asyncio.gather(
            *(self.resolve(owner_id, selection) for selection in selections)
        )
        return tuple(mounts)

    @staticmethod
    def get_all(context: _StudioToolContext) -> tuple[SessionEnvironmentMount, ...]:
        raw_mounts = getattr(context, "environment_mounts", ())
        if isinstance(raw_mounts, tuple) and all(
            isinstance(item, SessionEnvironmentMount) for item in raw_mounts
        ):
            mounts = raw_mounts
        elif isinstance(raw_mounts, list) and all(
            isinstance(item, SessionEnvironmentMount) for item in raw_mounts
        ):
            mounts = tuple(raw_mounts)
        else:
            mounts = ()
        if not mounts:
            legacy_mount = getattr(context, "environment_mount", None)
            if isinstance(legacy_mount, SessionEnvironmentMount):
                mounts = (legacy_mount,)
        if not mounts:
            raise ValueError("当前会话尚未挂载可执行环境。")
        return mounts

    @classmethod
    def get(
        cls,
        context: _StudioToolContext,
        environment_id: str = "",
    ) -> SessionEnvironmentMount:
        mounts = cls.get_all(context)
        selected_id = environment_id.strip()
        if not selected_id:
            if len(mounts) == 1:
                return mounts[0]
            raise ValueError("当前会话挂载了多个环境，必须指定 environment_id。")
        for mount in mounts:
            if mount.environment_id == selected_id:
                return mount
        raise ValueError("该环境未挂载到当前会话。")


def _resource_location(resources: object) -> tuple[str, str]:
    if hasattr(resources, "model_dump"):
        resources = resources.model_dump(mode="python")  # type: ignore[union-attr]
    if not isinstance(resources, dict):
        return "", ""
    provider = resources.get("provider")
    region = resources.get("region")
    return (
        provider.strip() if isinstance(provider, str) else "",
        region.strip() if isinstance(region, str) else "",
    )


def _string_value(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__ = [
    "SessionEnvironmentMount",
    "SessionEnvironmentMountRegistry",
    "SessionEnvironmentSelection",
    "SessionEnvironmentSelections",
]
