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

"""Evaluation APIs backed exclusively by Studio TOS storage"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any, Literal
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from veadk.integrations.agentkit.evaluation.feedback import (
    extract_feedback_sample,
    feedback_state_key,
)

from .models import Sample, public_record
from .repository import EvaluationError, EvaluationStorage, sample_id


class Input(BaseModel):
    model_config = ConfigDict(
        extra="forbid", populate_by_name=True, str_strip_whitespace=True
    )


class SetInput(Input):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=4000)


class SetUpdate(SetInput):
    revision: str = Field(min_length=1)


class SampleInput(Input):
    evaluation_set_id: str = Field(alias="evaluationSetId", min_length=1)
    input: str = Field(min_length=1, max_length=200_000)
    output: str = Field(min_length=1, max_length=200_000)
    reference_output: str = Field(
        default="", alias="referenceOutput", max_length=200_000
    )
    comment: str = Field(default="", max_length=20_000)


class SampleUpdate(SampleInput):
    revision: str = Field(min_length=1)


class FeedbackInput(Input):
    runtime_id: str = Field(alias="runtimeId", min_length=1)
    region: str = ""
    app_name: str = Field(alias="appName", min_length=1)
    user_id: str = Field(alias="userId", min_length=1)
    session_id: str = Field(alias="sessionId", min_length=1)
    event_id: str = Field(alias="eventId", min_length=1)
    rating: Literal["good", "bad"] | None
    comment: str = Field(default="", max_length=20_000)


class DeleteInput(Input):
    runtime_id: str = Field(alias="runtimeId", min_length=1)
    region: str = ""
    app_name: str = Field(alias="appName", min_length=1)
    item_ids: list[str] = Field(alias="itemIds", min_length=1, max_length=200)


class FeedbackStateInput(Input):
    runtime_id: str = Field(alias="runtimeId", min_length=1)
    region: str = ""
    user_id: str = Field(alias="userId", min_length=1)
    session_id: str = Field(alias="sessionId", min_length=1)
    event_ids: list[str] = Field(alias="eventIds", max_length=200)


def case_view(sample: Sample, runtime_id: str, set_names: dict[str, str]) -> dict:
    annotated_bad = (
        sample.source == "user"
        and sample.kind == "bad"
        and bool(sample.comment.strip())
    )
    return {
        **public_record(sample),
        "itemKey": sample.id,
        "runtimeId": runtime_id,
        "agentName": "",
        "workspaceId": "",
        "evaluationSetName": set_names.get(sample.evaluation_set_id, ""),
        "score": 0 if annotated_bad else sample.score,
        "reason": sample.comment if annotated_bad else sample.reason,
    }


def mount_routes(
    app: FastAPI,
    *,
    storage: EvaluationStorage,
    authorize: Callable,
    principal: Callable,
    runtime_request: Callable,
    normalize_region: Callable,
) -> None:
    async def storage_error(_request: Request, error: Exception) -> JSONResponse:
        if not isinstance(error, EvaluationError):
            raise error
        return JSONResponse({"detail": str(error)}, status_code=error.status)

    app.add_exception_handler(EvaluationError, storage_error)

    def repository(request: Request, runtime_id: str, region: str):
        authorize(request, runtime_id, normalize_region(region))
        return storage.for_runtime(runtime_id)

    def actor(request: Request) -> str:
        value = principal(request)
        return str(value.owner_id) if value else "local"

    @app.get("/web/evaluation/sets")
    async def list_sets(
        request: Request, runtimeId: str = Query(min_length=1), region: str = ""
    ):
        repo = repository(request, runtimeId, region)
        sets, samples = await asyncio.gather(repo.list_sets(), repo.list_samples())
        return {
            "items": [
                {
                    **public_record(item),
                    "itemCount": sum(
                        row.evaluation_set_id == item.id for row in samples
                    ),
                }
                for item in sets
            ]
        }

    @app.post("/web/evaluation/sets", status_code=201)
    async def create_set(
        data: SetInput,
        request: Request,
        runtimeId: str = Query(min_length=1),
        region: str = "",
    ):
        repo = repository(request, runtimeId, region)
        return public_record(
            await repo.create_set(data.name, data.description, actor(request))
        )

    @app.post("/web/evaluation/sets/defaults")
    async def ensure_defaults(
        request: Request, runtimeId: str = Query(min_length=1), region: str = ""
    ):
        return {
            "items": [
                public_record(item)
                for item in await repository(
                    request, runtimeId, region
                ).ensure_defaults()
            ]
        }

    @app.get("/web/evaluation/sets/{identifier}")
    async def get_set(
        identifier: str,
        request: Request,
        runtimeId: str = Query(min_length=1),
        region: str = "",
    ):
        return public_record(
            await repository(request, runtimeId, region).get_set(identifier)
        )

    @app.patch("/web/evaluation/sets/{identifier}")
    async def update_set(
        identifier: str,
        data: SetUpdate,
        request: Request,
        runtimeId: str = Query(min_length=1),
        region: str = "",
    ):
        repo = repository(request, runtimeId, region)
        return public_record(
            await repo.update_set(
                identifier, data.name, data.description, data.revision
            )
        )

    @app.delete("/web/evaluation/sets/{identifier}")
    async def delete_set(
        identifier: str,
        request: Request,
        revision: str = Query(min_length=1),
        runtimeId: str = Query(min_length=1),
        region: str = "",
    ):
        await repository(request, runtimeId, region).delete_set(identifier, revision)
        return {"deleted": True}

    @app.get("/web/evaluation/samples")
    async def list_samples(
        request: Request,
        runtimeId: str = Query(min_length=1),
        region: str = "",
        setId: str | None = None,
        q: str = "",
        source: Literal["user", "auto"] | None = None,
        page: int = Query(default=1, ge=1),
        pageSize: int = Query(default=50, ge=1, le=200),
    ):
        repo = repository(request, runtimeId, region)
        if setId:
            await repo.get_set(setId)
        rows = [
            row
            for row in await repo.list_samples()
            if (not setId or row.evaluation_set_id == setId)
            and (not source or row.source == source)
            and (
                not q
                or q.casefold()
                in "\n".join((row.input, row.output, row.comment)).casefold()
            )
        ]
        offset = (page - 1) * pageSize
        return {
            "items": [public_record(row) for row in rows[offset : offset + pageSize]],
            "total": len(rows),
            "page": page,
            "pageSize": pageSize,
        }

    @app.post("/web/evaluation/samples", status_code=201)
    async def create_sample(
        data: SampleInput,
        request: Request,
        runtimeId: str = Query(min_length=1),
        region: str = "",
    ):
        repo = repository(request, runtimeId, region)
        sample = Sample(
            id=uuid4().hex, source="user", userId=actor(request), **data.model_dump()
        )
        return public_record(await repo.save_sample(sample))

    @app.get("/web/evaluation/samples/{identifier}")
    async def get_sample(
        identifier: str,
        request: Request,
        runtimeId: str = Query(min_length=1),
        region: str = "",
    ):
        return public_record(
            await repository(request, runtimeId, region).get_sample(identifier)
        )

    @app.patch("/web/evaluation/samples/{identifier}")
    async def update_sample(
        identifier: str,
        data: SampleUpdate,
        request: Request,
        runtimeId: str = Query(min_length=1),
        region: str = "",
    ):
        repo = repository(request, runtimeId, region)
        sample = await repo.get_sample(identifier)
        return public_record(
            await repo.save_sample(
                sample.model_copy(update=data.model_dump(exclude={"revision"})),
                data.revision,
            )
        )

    @app.delete("/web/evaluation/samples/{identifier}")
    async def delete_sample(
        identifier: str,
        request: Request,
        revision: str = Query(min_length=1),
        runtimeId: str = Query(min_length=1),
        region: str = "",
    ):
        return {
            "deleted": await repository(request, runtimeId, region).delete_sample(
                identifier, revision
            )
        }

    async def persist_feedback_state(
        request: Request, runtime: Any, data: FeedbackInput, value: dict
    ) -> None:
        try:
            await runtime_request(
                request,
                runtime=runtime,
                runtime_id=data.runtime_id,
                region=normalize_region(data.region),
                method="PATCH",
                path=f"apps/{quote(data.app_name, safe='')}/users/{quote(data.user_id, safe='')}/sessions/{quote(data.session_id, safe='')}",
                payload={"state_delta": {feedback_state_key(data.event_id): value}},
            )
        except HTTPException as error:
            if error.status_code != 404:
                raise
            value["statePersistence"] = "browser"

    @app.post("/web/evaluation/feedback-state")
    async def feedback_state(data: FeedbackStateInput, request: Request):
        current = principal(request)
        if current is None or data.user_id.casefold() not in current.identifiers:
            raise HTTPException(403, "只能读取当前用户的会话反馈")
        authorize(request, data.runtime_id, normalize_region(data.region), True)
        return await storage.for_runtime(data.runtime_id).feedback_states(
            data.user_id, data.session_id, list(dict.fromkeys(data.event_ids))
        )

    @app.post("/web/evaluation/feedback")
    async def feedback(data: FeedbackInput, request: Request):
        current = principal(request)
        if current is None or data.user_id.casefold() not in current.identifiers:
            raise HTTPException(403, "只能提交当前用户的会话反馈")
        region = normalize_region(data.region)
        runtime = authorize(request, data.runtime_id, region, True)
        repo = storage.for_runtime(data.runtime_id)
        identifier = sample_id("user", data.user_id, data.session_id, data.event_id)
        saved = None
        collection = None
        if data.rating is not None:
            session = await runtime_request(
                request,
                runtime=runtime,
                runtime_id=data.runtime_id,
                region=region,
                method="GET",
                path=f"apps/{quote(data.app_name, safe='')}/users/{quote(data.user_id, safe='')}/sessions/{quote(data.session_id, safe='')}",
            )
            try:
                sample = extract_feedback_sample(
                    session,
                    target_event_id=data.event_id,
                    runtime_id=data.runtime_id,
                    agent_name="",
                    user_id=data.user_id,
                )
            except ValueError as error:
                raise HTTPException(400, str(error)) from error
            saved = await repo.save_feedback(
                Sample(
                    id=identifier,
                    evaluationSetId=data.rating,
                    source="user",
                    kind=data.rating,
                    input=sample.input,
                    output=sample.output,
                    referenceOutput=sample.output if data.rating == "good" else "",
                    comment=data.comment,
                    userId=data.user_id,
                    sessionId=data.session_id,
                    messageId=data.event_id,
                    invocationId=sample.invocation_id,
                )
            )
            collection = await repo.get_set(saved.evaluation_set_id)
        else:
            await repo.delete_sample(identifier)
        value = {
            "rating": data.rating,
            "comment": data.comment if saved else "",
            "evaluationSetId": collection.id if collection else None,
            "evaluationSetName": collection.name if collection else None,
            "evaluationItemId": saved.id if saved else None,
            "workspaceId": None,
            "syncStatus": "synced",
            "statePersistence": "runtime",
            "updatedAt": time.time(),
        }
        await persist_feedback_state(request, runtime, data, value)
        return value

    @app.get("/web/evaluation/feedback-cases")
    async def feedback_cases(
        request: Request,
        runtimeId: str = Query(min_length=1),
        appName: str = "",
        region: str = "",
        page_size: int = Query(default=100, ge=1, le=200),
    ):
        repo = repository(request, runtimeId, region)
        sets, rows = await asyncio.gather(repo.list_sets(), repo.list_samples())
        names = {item.id: item.name for item in sets}
        default_ids = {item.id for item in sets if item.default_kind}
        rows = [row for row in rows if row.evaluation_set_id in default_ids]
        return {
            "runtimeId": runtimeId,
            "agentName": appName,
            "region": normalize_region(region),
            "projectName": "",
            "sets": [
                {
                    "kind": item.default_kind,
                    "evaluationSetId": item.id,
                    "evaluationSetName": item.name,
                    "workspaceId": "",
                    "itemCount": sum(row.evaluation_set_id == item.id for row in rows),
                }
                for item in sets
                if item.default_kind
            ],
            "items": [case_view(row, runtimeId, names) for row in rows[:page_size]],
        }

    @app.post("/web/evaluation/feedback-cases/delete")
    async def delete_feedback(data: DeleteInput, request: Request):
        repo = repository(request, data.runtime_id, data.region)
        runtime = authorize(request, data.runtime_id, normalize_region(data.region))
        count = 0
        for identifier in dict.fromkeys(data.item_ids):
            try:
                row = await repo.get_sample(identifier)
            except EvaluationError as error:
                if error.status == 404:
                    continue
                raise
            count += await repo.delete_sample(identifier, row.revision)
            if row.source == "user" and row.session_id and row.message_id:
                value = {
                    "rating": None,
                    "evaluationSetId": None,
                    "evaluationItemId": None,
                    "syncStatus": "synced",
                    "statePersistence": "runtime",
                    "updatedAt": time.time(),
                }
                await persist_feedback_state(
                    request,
                    runtime,
                    FeedbackInput(
                        runtimeId=data.runtime_id,
                        region=data.region,
                        appName=data.app_name,
                        userId=row.user_id,
                        sessionId=row.session_id,
                        eventId=row.message_id,
                        rating=None,
                    ),
                    value,
                )
        return {"deletedCount": count}
