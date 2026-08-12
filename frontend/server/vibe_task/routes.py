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

from __future__ import annotations

from collections.abc import Callable
import json
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from .models import CredentialUpload, CreateTaskRequest, IntentSummaryUpdate
from .service import VibeTaskError, VibeTaskService


def mount_vibe_task_routes(
    app: Any,
    owner_resolver: Callable[[Request], str],
    *,
    service: VibeTaskService | None = None,
) -> VibeTaskService:
    service = service or VibeTaskService()

    def handle(error: VibeTaskError) -> HTTPException:
        return HTTPException(status_code=error.status_code, detail=error.detail())

    @app.get("/web/vibe/capabilities")
    async def capabilities(request: Request) -> dict[str, object]:
        owner_resolver(request)
        return {
            "enabled": True,
            "sandboxTtlSeconds": 28_800,
            "maxCloudAttempts": 3,
            "intentSummaryPath": "/home/gem/.vibe/task/intent-summary.json",
            "evaluationEnabled": False,
        }

    @app.post("/web/vibe/tasks")
    async def create_task(body: CreateTaskRequest, request: Request) -> dict[str, object]:
        try:
            status = await service.create(owner_resolver(request), body)
            return status.model_dump(by_alias=True)
        except VibeTaskError as error:
            raise handle(error) from error

    @app.get("/web/vibe/tasks")
    async def list_tasks(request: Request) -> dict[str, object]:
        return {"tasks": [item.model_dump(by_alias=True) for item in await service.list(owner_resolver(request))]}

    @app.get("/web/vibe/tasks/{task_id}")
    async def get_task(task_id: str, request: Request) -> dict[str, object]:
        try:
            return (await service.require(owner_resolver(request), task_id)).model_dump(by_alias=True)
        except VibeTaskError as error:
            raise handle(error) from error

    @app.post("/web/vibe/tasks/{task_id}/credentials")
    async def credentials(task_id: str, body: CredentialUpload, request: Request) -> dict[str, object]:
        try:
            return (await service.configure_credentials(owner_resolver(request), task_id, body)).model_dump(by_alias=True)
        except VibeTaskError as error:
            raise handle(error) from error

    @app.get("/web/vibe/tasks/{task_id}/intent-summary")
    async def get_intent(task_id: str, request: Request) -> dict[str, object]:
        try:
            return (await service.get_intent(owner_resolver(request), task_id)).model_dump(by_alias=True)
        except VibeTaskError as error:
            raise handle(error) from error

    @app.put("/web/vibe/tasks/{task_id}/intent-summary")
    async def update_intent(task_id: str, body: IntentSummaryUpdate, request: Request) -> dict[str, object]:
        try:
            return (await service.update_intent(owner_resolver(request), task_id, body)).model_dump(by_alias=True)
        except VibeTaskError as error:
            raise handle(error) from error

    @app.get("/web/vibe/tasks/{task_id}/events")
    async def events(task_id: str, request: Request) -> StreamingResponse:
        owner_id = owner_resolver(request)
        raw = request.headers.get("last-event-id", "0")
        try:
            after = max(0, int(raw))
            await service.require(owner_id, task_id)
        except (ValueError, VibeTaskError) as error:
            if isinstance(error, VibeTaskError):
                raise handle(error) from error
            raise HTTPException(status_code=400, detail="Last-Event-ID must be an integer") from error

        async def stream():
            async for event in service.events(owner_id, task_id, after):
                payload = event.model_dump(by_alias=True)
                yield f"id: {event.sequence}\nevent: {event.event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/web/vibe/tasks/{task_id}/stop")
    async def stop(task_id: str, request: Request) -> dict[str, object]:
        try:
            return (await service.stop(owner_resolver(request), task_id)).model_dump(by_alias=True)
        except VibeTaskError as error:
            raise handle(error) from error

    @app.delete("/web/vibe/tasks/{task_id}")
    async def delete(task_id: str, request: Request) -> Response:
        try:
            deleted = await service.delete(owner_resolver(request), task_id)
        except VibeTaskError as error:
            raise handle(error) from error
        if not deleted:
            raise HTTPException(status_code=404, detail="Task not found")
        return Response(status_code=204)

    return service
