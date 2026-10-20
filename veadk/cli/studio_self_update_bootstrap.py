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

"""Lightweight Studio self-update routes for the cold-start path."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from threading import Lock
from typing import Any

from fastapi import HTTPException, Request

from veadk.utils.cloud_provider import CloudProvider
from veadk.version import VERSION


Credentials = tuple[str, str, str | None]
CredentialResolver = Callable[[], Credentials]
AdminGuard = Callable[[Request], None]
_UPDATE_HEADER = "X-VeADK-Studio-Update"


def current_studio_display_version() -> str:
    """Return the display version without importing the updater runtime."""
    release_version = os.getenv("VEADK_STUDIO_RELEASE_VERSION", "bundled")
    return VERSION if release_version == "bundled" else release_version


class LazyStudioSelfUpdater:
    """Construct the full updater only when an administrator requests it."""

    def __init__(
        self,
        *,
        provider: CloudProvider,
        credential_resolver: CredentialResolver,
        branding_logo: Any | None,
    ) -> None:
        self._provider: CloudProvider = provider
        self._credential_resolver = credential_resolver
        self._branding_logo = branding_logo
        self._delegate: Any | None = None
        self._lock = Lock()

    def _resolve(self) -> Any:
        if self._delegate is not None:
            return self._delegate
        with self._lock:
            if self._delegate is None:
                from veadk.cli.studio_self_update import (
                    StudioSelfUpdater,
                    StudioUpdateSettings,
                )

                self._delegate = StudioSelfUpdater(
                    settings=StudioUpdateSettings.from_env(provider=self._provider),
                    credential_resolver=self._credential_resolver,
                    branding_logo=self._branding_logo,
                )
        return self._delegate

    def status(self, **kwargs: Any) -> dict[str, Any]:
        return self._resolve().status(**kwargs)

    def permission_precheck(self) -> dict[str, Any]:
        return self._resolve().permission_precheck()

    def submit_version(self, version: str | None) -> Any:
        return self._resolve().submit_version(version)


def _is_release_version(value: str) -> bool:
    return len(value) == 14 and value.isdigit()


def _raise_permission_error(error: Exception) -> None:
    from veadk.cli.studio_release import StudioReleaseError

    if isinstance(error, StudioReleaseError):
        raise HTTPException(status_code=502, detail=str(error)) from error
    raise error


def _raise_submit_error(error: Exception) -> None:
    from veadk.cli.studio_release import StudioReleaseError
    from veadk.cli.studio_self_update import (
        StudioUpdateConflict,
        StudioUpdatePermissionRequired,
    )

    if isinstance(error, (StudioUpdateConflict, StudioUpdatePermissionRequired)):
        raise HTTPException(status_code=409, detail=str(error)) from error
    if isinstance(error, StudioReleaseError):
        raise HTTPException(status_code=502, detail=str(error)) from error
    raise error


def mount_lazy_studio_update_routes(
    app: Any,
    updater: LazyStudioSelfUpdater,
    require_admin: AdminGuard,
) -> None:
    """Mount the existing update API without importing its implementation."""

    @app.get("/web/studio-update")
    async def _studio_update_status(request: Request) -> dict[str, Any]:
        require_admin(request)
        target_version = request.query_params.get("targetVersion")
        if target_version and not _is_release_version(target_version):
            raise HTTPException(status_code=400, detail="版本号格式无效")
        raw_started_at = request.query_params.get("startedAt")
        try:
            started_at = int(raw_started_at) if raw_started_at else None
        except ValueError as error:
            raise HTTPException(status_code=400, detail="更新时间格式无效") from error
        if started_at is not None and started_at <= 0:
            raise HTTPException(status_code=400, detail="更新时间格式无效")
        return await asyncio.to_thread(
            updater.status,
            target_version=target_version,
            started_at=started_at,
        )

    @app.get("/web/studio-update/permissions")
    async def _studio_update_permissions(request: Request) -> dict[str, Any]:
        require_admin(request)
        try:
            return await asyncio.to_thread(updater.permission_precheck)
        except Exception as error:
            _raise_permission_error(error)
            raise

    @app.post("/web/studio-update", status_code=202)
    async def _studio_update_start(request: Request) -> dict[str, Any]:
        require_admin(request)
        if request.headers.get(_UPDATE_HEADER) != "1":
            raise HTTPException(
                status_code=403,
                detail="Studio update header is required",
            )
        try:
            version = None
            if request.headers.get("content-type", "").startswith("application/json"):
                payload = await request.json()
                if not isinstance(payload, dict):
                    raise HTTPException(status_code=400, detail="请求格式无效")
                raw_version = payload.get("version")
                if raw_version is not None and not isinstance(raw_version, str):
                    raise HTTPException(status_code=400, detail="版本号格式无效")
                version = raw_version
            manifest = await asyncio.to_thread(updater.submit_version, version)
        except HTTPException:
            raise
        except Exception as error:
            _raise_submit_error(error)
            raise
        return {
            "accepted": True,
            "version": manifest.version,
            "gitSha": manifest.git_sha,
        }
