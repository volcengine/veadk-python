"""Studio BFF automatic evaluation module."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from .datasets import ensure_feedback_sets
from .model_gateway import StructuredEvaluationModels
from .models import RunSseActivity
from .repository import (
    AgentKitAutoEvaluationRepository,
    InMemoryOptimizationRepository,
)
from .routes import mount_routes
from .service import EvaluationAutomationService
from .sse import RunSseObservation, observed_sse_stream

OpenApiPost = Callable[..., Awaitable[dict[str, Any]]]


def create_service(
    *,
    openapi_post: OpenApiPost,
    quiet_seconds: float = 300,
) -> EvaluationAutomationService:
    models = StructuredEvaluationModels()
    optimizations = InMemoryOptimizationRepository()

    async def runtime_get(
        activity: RunSseActivity,
        path: str,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        authorization = activity.runtime_authorization.get_secret_value()
        if authorization:
            headers["Authorization"] = authorization
        target = f"{activity.runtime_endpoint}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(target, headers=headers)
        if response.status_code >= 400:
            raise RuntimeError(f"Runtime returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as error:
            raise RuntimeError("Runtime returned a non-JSON response") from error
        if not isinstance(payload, dict):
            raise TypeError("Runtime returned an invalid JSON response")
        return payload

    async def case_repository(
        activity: RunSseActivity,
    ) -> AgentKitAutoEvaluationRepository:
        async def post(
            *,
            action: str,
            payload: dict[str, Any],
            query: dict[str, str] | None = None,
        ) -> dict[str, Any]:
            return await openapi_post(
                region=activity.region,
                action=action,
                payload=payload,
                query=query,
            )

        return AgentKitAutoEvaluationRepository(
            post,
            project_name=activity.project_name,
        )

    return EvaluationAutomationService(
        evaluator=models,
        optimizer=models,
        optimization_repository=optimizations,
        runtime_get=runtime_get,
        case_repository=case_repository,
        quiet_seconds=quiet_seconds,
    )


__all__ = [
    "EvaluationAutomationService",
    "RunSseActivity",
    "RunSseObservation",
    "create_service",
    "ensure_feedback_sets",
    "mount_routes",
    "observed_sse_stream",
]
