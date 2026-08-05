"""Evaluation-set initialization for Studio deployments."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from veadk.integrations.agentkit.evaluation import (
    AgentKitEvaluationDatasetsClient,
)

OpenApiPost = Callable[..., Awaitable[dict[str, Any]]]


async def ensure_feedback_sets(
    *,
    openapi_post: OpenApiPost,
    region: str,
    project_name: str,
    agent_name: str,
) -> list[str]:
    """Idempotently ensure the Studio Agent's good and bad feedback sets."""

    async def post(
        *,
        action: str,
        payload: dict[str, Any],
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return await openapi_post(
            region=region,
            action=action,
            payload=payload,
            query=query,
        )

    client = AgentKitEvaluationDatasetsClient(
        post,
        project_name=project_name,
    )
    created = []
    for rating in ("good", "bad"):
        evaluation_set = await client.ensure_feedback_set(agent_name, rating)
        created.append(evaluation_set.name)
    return created
