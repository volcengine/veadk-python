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

"""Authenticated Agent review operations with complete upstream error bodies."""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Callable
from typing import Any, Literal

from fastapi import HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from .service import AgentReviewService, ReviewActor


class ReviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    region: str = Field(min_length=1, max_length=64)
    message: str = Field(default="", max_length=1000)
    comment: str = Field(default="", max_length=1000)


class DecisionBody(ReviewBody):
    applicationId: str = Field(min_length=1, max_length=64)
    decision: Literal["approved", "returned"]
    reason: str = Field(default="", max_length=1000)


def cloud_error(error: Exception) -> Response:
    current: BaseException = error
    seen: set[int] = set()
    while current.__cause__ is not None and id(current) not in seen:
        seen.add(id(current))
        current = current.__cause__
    raw = getattr(current, "body", None) or str(current)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if not isinstance(raw, str):
        raw = json.dumps(raw, ensure_ascii=False)
    # Older AgentKit clients embed the original response bytes in RuntimeError
    match = re.search(r"(b[\"'].*[\"'])$", raw, re.DOTALL)
    if match:
        try:
            value = ast.literal_eval(match.group(1))
            if isinstance(value, bytes):
                raw = value.decode("utf-8", errors="replace")
        except (SyntaxError, ValueError):
            pass
    status = (
        getattr(current, "status_code", None) or getattr(current, "status", None) or 502
    )
    try:
        data = json.loads(raw)
        status = (
            data.get("ResponseMetadata", {}).get("Error", {}).get("HTTPCode", status)
        )
        media_type = "application/json"
    except (ValueError, AttributeError):
        media_type = "text/plain"
    return Response(
        raw,
        status_code=status if isinstance(status, int) and 400 <= status <= 599 else 502,
        media_type=media_type,
    )


def mount_agent_review_routes(
    app: Any,
    service: AgentReviewService,
    identity: Callable[[Request], ReviewActor],
    region: Callable[[str], str],
    invalidate: Callable[[], None],
) -> None:
    async def invoke(call: Callable[[], Any], *, mutation: bool = False) -> Any:
        try:
            result = await run_in_threadpool(call)
            return result
        except HTTPException:
            raise
        except Exception as error:  # noqa: BLE001 - preserve arbitrary SDK error bodies at the HTTP boundary
            return cloud_error(error)
        finally:
            if mutation:
                invalidate()

    @app.get("/web/agent-reviews")
    async def list_reviews(
        request: Request,
        region_name: str = Query(alias="region", min_length=1, max_length=64),
    ):
        actor = identity(request)
        resolved = region(region_name)
        return await invoke(lambda: {"items": service.list(actor, resolved)})

    @app.get("/web/agent-reviews/{runtime_id}")
    async def read_review(
        runtime_id: str,
        request: Request,
        region_name: str = Query(alias="region", min_length=1, max_length=64),
    ):
        actor = identity(request)
        resolved = region(region_name)
        return await invoke(
            lambda: {"application": service.read(actor, resolved, runtime_id)}
        )

    @app.post("/web/agent-reviews/{runtime_id}/submit")
    async def submit(runtime_id: str, body: ReviewBody, request: Request):
        actor = identity(request)
        resolved = region(body.region)
        return await invoke(
            lambda: service.submit(actor, resolved, runtime_id, body.message),
            mutation=True,
        )

    @app.post("/web/agent-reviews/{runtime_id}/decision")
    async def decide(runtime_id: str, body: DecisionBody, request: Request):
        actor = identity(request)
        resolved = region(body.region)
        return await invoke(
            lambda: service.decide(
                actor,
                resolved,
                runtime_id,
                body.applicationId,
                body.decision,
                body.reason,
                body.comment,
            ),
            mutation=True,
        )

    @app.post("/web/agent-reviews/{runtime_id}/publish")
    async def publish(runtime_id: str, body: ReviewBody, request: Request):
        actor = identity(request)
        resolved = region(body.region)
        return await invoke(
            lambda: service.publish(actor, resolved, runtime_id, body.comment),
            mutation=True,
        )

    @app.post("/web/agent-reviews/{runtime_id}/withdraw")
    async def withdraw(runtime_id: str, body: ReviewBody, request: Request):
        actor = identity(request)
        resolved = region(body.region)
        return await invoke(
            lambda: service.withdraw(actor, resolved, runtime_id), mutation=True
        )

    @app.post("/web/agent-reviews/{runtime_id}/unpublish")
    async def unpublish(runtime_id: str, body: ReviewBody, request: Request):
        actor = identity(request)
        resolved = region(body.region)
        return await invoke(
            lambda: service.unpublish(actor, resolved, runtime_id), mutation=True
        )
