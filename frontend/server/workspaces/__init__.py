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

"""Studio workspace backend composition."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from frontend.server.environments.repository import TosEnvironmentRepository
from frontend.server.storage import StudioProvider, StudioStorageConfig
from frontend.server.storage.tos import CredentialResolver, create_tos_client_factory

from .repository import TosWorkspaceRepository
from .routes import mount_workspace_routes
from .service import WorkspaceService


def create_workspace_service(
    *,
    provider: StudioProvider = "volcengine",
    resolve_credentials: CredentialResolver | None = None,
    client_factory: Callable[[], Any] | None = None,
    environment: Mapping[str, str] | None = None,
) -> WorkspaceService:
    storage = StudioStorageConfig.from_env(provider, environment)
    if not storage.configured:
        return WorkspaceService(
            None, None, unavailable_reason=storage.unavailable_reason
        )
    if client_factory is None:
        if resolve_credentials is None:
            return WorkspaceService(
                None,
                None,
                unavailable_reason="管理员未配置工作区存储凭据。",
            )
        client_factory = create_tos_client_factory(storage, resolve_credentials)
    return WorkspaceService(
        TosWorkspaceRepository(bucket=storage.bucket, client_factory=client_factory),
        TosEnvironmentRepository(bucket=storage.bucket, client_factory=client_factory),
    )


__all__ = ["WorkspaceService", "create_workspace_service", "mount_workspace_routes"]
