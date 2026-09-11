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

"""Native Skill version endpoints using the Skill management request boundary."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Query, Request

from .models import SkillIdentity
from .versions import SkillVersionRepository


def mount_skill_version_routes(
    app: Any,
    versions: SkillVersionRepository,
    identity_resolver: Callable[[Request], SkillIdentity],
    invoke: Callable[[Callable[[], Any]], Awaitable[Any]],
    read_archive: Callable[[Request], Awaitable[bytes]],
) -> None:
    @app.get("/web/skill-management/spaces/{space_id}/skills/{skill_id}/versions")
    async def list_versions(
        request: Request,
        space_id: str,
        skill_id: str,
        region: str = Query(..., min_length=1, max_length=64),
    ) -> Any:
        identity = identity_resolver(request)
        return await invoke(
            lambda: versions.list(
                identity,
                region=region,
                space_id=space_id,
                skill_id=skill_id,
            )
        )

    @app.post("/web/skill-management/spaces/{space_id}/skills/{skill_id}/versions")
    async def upload_version(
        request: Request,
        space_id: str,
        skill_id: str,
        region: str = Query(..., min_length=1, max_length=64),
    ) -> Any:
        identity = identity_resolver(request)
        content = await read_archive(request)
        return await invoke(
            lambda: versions.upload(
                identity,
                region=region,
                space_id=space_id,
                skill_id=skill_id,
                content=content,
            )
        )
