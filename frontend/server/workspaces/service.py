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

"""Workspace CRUD and reusable environment membership."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from frontend.server.environments.repository import (
    EnvironmentNotFound,
    TosEnvironmentRepository,
)

from .models import WorkspaceInput, WorkspacePatch, WorkspaceRecord
from .repository import TosWorkspaceRepository, WorkspaceStorageUnavailable


class WorkspaceService:
    def __init__(
        self,
        repository: TosWorkspaceRepository | None,
        environments: TosEnvironmentRepository | None,
        *,
        unavailable_reason: str = "管理员未配置工作区持久化存储。",
    ) -> None:
        self._repository = repository
        self._environments = environments
        self._unavailable_reason = unavailable_reason

    async def list(self, owner_id: str) -> list[WorkspaceRecord]:
        return await self._require_repository().list(owner_id)

    async def get(self, owner_id: str, workspace_id: str) -> WorkspaceRecord:
        return await self._require_repository().get(owner_id, workspace_id)

    async def create(self, owner_id: str, body: WorkspaceInput) -> WorkspaceRecord:
        await self._validate_environments(owner_id, body.environment_ids)
        now = _now()
        return await self._require_repository().create(
            WorkspaceRecord(
                **body.model_dump(),
                id=uuid4().hex,
                ownerId=owner_id,
                createdAt=now,
                updatedAt=now,
            )
        )

    async def update(
        self, owner_id: str, workspace_id: str, patch: WorkspacePatch
    ) -> WorkspaceRecord:
        repository = self._require_repository()
        current = await repository.get(owner_id, workspace_id)
        values = current.model_dump()
        changes = patch.model_dump(exclude_unset=True)
        if "environment_ids" in changes:
            await self._validate_environments(owner_id, changes["environment_ids"])
        values.update(changes)
        values["updated_at"] = _now()
        return await repository.update(WorkspaceRecord.model_validate(values))

    async def delete(self, owner_id: str, workspace_id: str) -> None:
        await self._require_repository().delete(owner_id, workspace_id)

    async def add_environment(
        self, owner_id: str, workspace_id: str, environment_id: str
    ) -> WorkspaceRecord:
        current = await self.get(owner_id, workspace_id)
        if environment_id in current.environment_ids:
            return current
        return await self.update(
            owner_id,
            workspace_id,
            WorkspacePatch(environmentIds=[*current.environment_ids, environment_id]),
        )

    async def remove_environment(
        self, owner_id: str, workspace_id: str, environment_id: str
    ) -> WorkspaceRecord:
        current = await self.get(owner_id, workspace_id)
        return await self.update(
            owner_id,
            workspace_id,
            WorkspacePatch(
                environmentIds=[
                    item for item in current.environment_ids if item != environment_id
                ]
            ),
        )

    async def workspace_names_for_environment(
        self, owner_id: str, environment_id: str
    ) -> list[str]:
        return [
            workspace.name
            for workspace in await self.list(owner_id)
            if environment_id in workspace.environment_ids
        ]

    async def _validate_environments(
        self, owner_id: str, environment_ids: list[str]
    ) -> None:
        environments = self._require_environments()
        for environment_id in environment_ids:
            try:
                await environments.get(owner_id, environment_id)
            except EnvironmentNotFound as error:
                raise ValueError(f"环境 {environment_id} 不存在或无权访问。") from error

    def _require_repository(self) -> TosWorkspaceRepository:
        if self._repository is None:
            raise WorkspaceStorageUnavailable(self._unavailable_reason)
        return self._repository

    def _require_environments(self) -> TosEnvironmentRepository:
        if self._environments is None:
            raise WorkspaceStorageUnavailable(self._unavailable_reason)
        return self._environments


def _now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = ["WorkspaceService"]
