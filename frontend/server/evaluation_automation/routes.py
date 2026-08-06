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

"""FastAPI routes owned by Studio evaluation automation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Query, Request

from .service import EvaluationAutomationService


def mount_routes(
    app: Any,
    service: EvaluationAutomationService,
    authorize: Callable[[Request, str, str], Any],
) -> None:
    @app.get("/web/evaluation/statuses")
    async def get_statuses(
        request: Request,
        runtimeId: str = Query(..., min_length=1),
        appName: str = Query(..., min_length=1),
        userId: str = Query(..., min_length=1),
        region: str = Query(default="cn-beijing", min_length=1),
    ) -> dict[str, Any]:
        authorize(request, runtimeId, region)
        statuses = service.list_statuses(
            runtime_id=runtimeId,
            app_name=appName,
            user_id=userId,
        )
        return {
            "runtimeId": runtimeId,
            "appName": appName,
            "userId": userId,
            "items": [
                status.model_dump(mode="json", by_alias=True) for status in statuses
            ],
        }

    @app.get("/web/evaluation/optimizations")
    async def get_optimizations(
        request: Request,
        runtimeId: str = Query(..., min_length=1),
        appName: str = Query(..., min_length=1),
        region: str = Query(default="cn-beijing", min_length=1),
    ) -> dict[str, Any]:
        authorize(request, runtimeId, region)
        snapshot = service.get_optimizations(runtimeId, appName)
        if snapshot is None:
            return {
                "runtimeId": runtimeId,
                "appName": appName,
                "generatedAt": None,
                "optimizerVersion": None,
                "sourceItemKeys": [],
                "groups": [],
            }
        return snapshot.model_dump(mode="json", by_alias=True)
