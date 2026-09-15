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

"""Authenticated submission and observation of short-lived build tasks."""

from __future__ import annotations

import json
import hashlib
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from .models import Run
from .repository import RunConflict, RunNotFound
from .service import RunService


def mount_run_routes(
    app: FastAPI,
    *,
    prefix: str,
    service: RunService,
    owner_resolver: Callable[[Request], str],
    prepare: Callable[[str, str], Awaitable[str]],
    redact_message: Callable[[str], str],
) -> None:
    repository = service.repository

    def owner(request: Request) -> str:
        value = owner_resolver(request)
        if not value:
            raise HTTPException(401, "请先登录。")
        return value

    async def body(request: Request, keys: set[str]) -> dict[str, str]:
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 128 * 1024:
                raise HTTPException(413, "消息过长。")
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as error:
            raise HTTPException(422, "请求不是有效 JSON。") from error
        if not isinstance(value, dict) or set(value) != keys:
            raise HTTPException(422, "请求字段无效。")
        if any(
            not isinstance(value[key], str) or not value[key].strip() for key in keys
        ):
            raise HTTPException(422, "请求字段不能为空。")
        if (
            len(value.get("message", "")) > 100_000
            or len(value.get("requestId", value.get("clientId", ""))) > 128
        ):
            raise HTTPException(422, "消息或标识过长。")
        return value

    async def owned(request: Request, run_id: str) -> Run:
        try:
            return await repository.get(owner(request), run_id)
        except RunNotFound as error:
            raise HTTPException(404, "任务不存在。") from error

    @app.post(f"{prefix}/sessions/{{session_id}}/runs", status_code=202)
    async def create(session_id: str, request: Request) -> dict[str, Any]:
        identity = owner(request)
        value = await body(request, {"message", "requestId"})
        # Ownership is checked against the environment before accepting remote work.
        thread_id = await prepare(session_id, identity)
        previous = await repository.session_runs(identity, session_id)
        if previous and previous[-1].thread_id:
            thread_id = previous[-1].thread_id
        try:
            run = await repository.create(
                identity,
                session_id,
                value["requestId"],
                redact_message(value["message"].strip()),
                thread_id=thread_id,
                message_digest=hashlib.sha256(
                    value["message"].strip().encode()
                ).hexdigest(),
            )
        except RunConflict as error:
            raise HTTPException(409, str(error)) from error
        service.launch(run)
        return run.public()

    @app.get(f"{prefix}/sessions/{{session_id}}/runs")
    async def list_runs(session_id: str, request: Request) -> dict[str, Any]:
        runs = await repository.session_runs(owner(request), session_id)
        return {"runs": [run.public() for run in runs]}

    @app.get(f"{prefix}/sessions/{{session_id}}/runs/current")
    async def current(session_id: str, request: Request) -> dict[str, Any]:
        runs = await repository.session_runs(owner(request), session_id)
        return {"run": runs[-1].public() if runs else None}

    @app.get(f"{prefix}/runs")
    async def active_runs(request: Request) -> dict[str, Any]:
        return {
            "runs": [
                run.public()
                for run in await repository.active_for_owner(owner(request))
            ]
        }

    @app.get(f"{prefix}/runs/{{run_id}}")
    async def detail(run_id: str, request: Request) -> dict[str, Any]:
        return (await owned(request, run_id)).public()

    @app.get(f"{prefix}/runs/{{run_id}}/events")
    async def events(
        run_id: str, request: Request, after: int = 0
    ) -> StreamingResponse:
        run = await owned(request, run_id)
        if after < 0 or after > run.last_seq:
            raise HTTPException(422, "事件游标无效。")

        async def stream():
            async for event in service.subscribe(run.owner_id, run_id, after=after):
                if event is None:
                    yield ": heartbeat\n\n"
                else:
                    payload = {**event["payload"], "runId": run_id, "seq": event["seq"]}
                    yield f"id: {event['seq']}\nevent: {event['type']}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            yield "event: done\ndata: {}\n\n"

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.post(f"{prefix}/runs/{{run_id}}/stop", status_code=202)
    async def stop(run_id: str, request: Request) -> dict[str, Any]:
        run = await owned(request, run_id)
        return (await service.stop(run.owner_id, run_id)).public()

    @app.post(f"{prefix}/runs/{{run_id}}/resume", status_code=202)
    async def resume(run_id: str, request: Request) -> dict[str, Any]:
        run = await owned(request, run_id)
        try:
            return (await service.resume(run.owner_id, run_id)).public()
        except RunConflict as error:
            raise HTTPException(409, str(error)) from error

    @app.post(f"{prefix}/runs/{{run_id}}/inputs", status_code=202)
    async def steer(run_id: str, request: Request) -> dict[str, Any]:
        run = await owned(request, run_id)
        value = await body(request, {"message", "clientId"})
        try:
            item = await repository.add_input(
                run.owner_id,
                run_id,
                value["clientId"],
                redact_message(value["message"].strip()),
                message_digest=hashlib.sha256(
                    value["message"].strip().encode()
                ).hexdigest(),
            )
        except RunConflict as error:
            raise HTTPException(409, str(error)) from error
        service.launch(await repository.get(run.owner_id, run_id))
        return {
            "clientId": item["client_id"],
            "status": item["status"],
            "revision": item["revision"],
        }

    @app.delete(f"{prefix}/runs/{{run_id}}", status_code=204)
    async def delete(run_id: str, request: Request) -> Response:
        run = await owned(request, run_id)
        try:
            await repository.delete(run.owner_id, run_id)
        except RunConflict as error:
            raise HTTPException(409, str(error)) from error
        return Response(status_code=204)
