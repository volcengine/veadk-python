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
