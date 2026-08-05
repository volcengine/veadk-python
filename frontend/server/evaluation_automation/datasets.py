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
