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

"""FastAPI routes for agent usage statistics."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Query, Request

from veadk.utils.logger import get_logger

from .service import AgentUsageService, AgentUsageStorageUnavailable

logger = get_logger(__name__)


def mount_routes(
    app: Any,
    service: AgentUsageService,
    authorize: Callable[[Request, str, str], Any],
) -> None:
    @app.get("/web/agent-usage")
    async def get_agent_usage(
        request: Request,
        runtimeId: str = Query(..., min_length=1),
        region: str = Query(..., min_length=1),
        appName: str = Query(..., min_length=1),
        page: int = Query(default=1, ge=1),
        pageSize: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, Any]:
        authorize(request, runtimeId, region)
        try:
            summary = await service.get_summary(
                runtime_id=runtimeId,
                app_name=appName,
                page=page,
                page_size=pageSize,
            )
        except AgentUsageStorageUnavailable as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except Exception as error:
            logger.exception(
                "Failed to load Studio agent usage runtime_id=%s app_name=%s",
                runtimeId,
                appName,
            )
            raise HTTPException(
                status_code=502,
                detail="无法读取 Agent 用量统计，请稍后重试。",
            ) from error
        return summary.model_dump(mode="json", by_alias=True)
