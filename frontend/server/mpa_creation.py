"""Authorized Studio entry points for VeADK-owned MPA creation."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from veadk.integrations.mpa.managed.config import (
    ConfigurationError,
    load_studio_profile,
    validate_creation_resources,
    validate_image_reference,
    with_creation_resources,
)
from veadk.integrations.mpa.managed.credentials import load_volcengine_credentials
from veadk.integrations.mpa.managed.tasks import CreationTasks, TaskError, owner_key


def _studio_task_path() -> Path:
    return Path(
        os.getenv(
            "VEADK_MPA_TASK_DB",
            "/tmp/veadk-studio/mpa-creation.sqlite3",
        )
    )


class CreationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requestId: UUID
    agentId: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    description: str = Field(default="", max_length=512)
    region: str = Field(pattern=r"^cn-[a-z]+$", max_length=32)
    runtimeImage: str = Field(default="", max_length=1024)
    workerImage: str = Field(default="", max_length=1024)
    pgHost: str = Field(default="", max_length=255)
    pgPort: str = Field(default="", max_length=5)
    openvikingUrl: str = Field(default="", max_length=1024)
    openvikingResourceId: str = Field(default="", max_length=128)
    openvikingApiKey: str = Field(default="", max_length=512, repr=False)

    @field_validator("runtimeImage", "workerImage")
    @classmethod
    def validate_image(cls, value):
        return validate_image_reference(value)

    @model_validator(mode="after")
    def validate_resources(self):
        validate_creation_resources(self.model_dump())
        return self


def mount_mpa_creation_routes(
    app: FastAPI, *, owner, service: CreationTasks | None = None, supported=True
):
    tasks = service

    def get_tasks():
        nonlocal tasks
        if tasks is None:
            task_path = _studio_task_path()
            tasks = CreationTasks(task_path)
        return tasks

    def profile(region):
        if not supported:
            raise ConfigurationError("MPA creation requires the Volcengine provider")
        result = load_studio_profile(region=region)
        try:
            load_volcengine_credentials(result.managed.credential_file)
        except ValueError:
            raise ConfigurationError(
                "Configure server deployment credentials"
            ) from None
        return None, result

    @app.get("/web/mpa-creation/config")
    async def inspect(request: Request, region: str):
        owner(request)
        try:
            _, result = profile(region)
            return result.summary()
        except ConfigurationError as exc:
            return {"configured": False, "region": region, "error": str(exc)}

    @app.post("/web/mpa-creation/tasks", status_code=202)
    async def create(request: Request):
        identity = owner_key(owner(request))
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > 8192:
                raise HTTPException(413, "Creation request is too large")
        try:
            body = CreationRequest.model_validate_json(bytes(content))
        except ValidationError:
            raise HTTPException(422, "Invalid MPA creation request") from None
        try:
            path, config = profile(body.region)
            payload = body.model_dump(mode="json")
            with_creation_resources(config, payload)
            openviking_api_key = payload.pop("openvikingApiKey")
            resources = validate_creation_resources(
                {**payload, "openvikingApiKey": openviking_api_key}
            )
            images = config.image_defaults()
            for field in ("runtimeImage", "workerImage"):
                if payload[field]:
                    images[field] = payload[field]
                else:
                    payload.pop(field)
            for field in ("pgHost", "pgPort", "openvikingUrl", "openvikingResourceId"):
                if resources[field]:
                    payload[field] = resources[field]
                else:
                    payload.pop(field)
            return await get_tasks().start(
                identity,
                payload,
                config_path=path,
                timeout=config.managed.timeout_seconds,
                images=images,
                secrets={"openvikingApiKey": openviking_api_key},
            )
        except ConfigurationError as exc:
            raise HTTPException(400, str(exc)) from None
        except TaskError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.get("/web/mpa-creation/tasks/{task_id}")
    async def status(request: Request, task_id: str):
        identity = owner_key(owner(request))
        try:
            return get_tasks().get(identity, task_id)
        except TaskError:
            raise HTTPException(404, "Creation task not found") from None

    @app.post("/web/mpa-creation/tasks/{task_id}/cancel")
    async def cancel(request: Request, task_id: str):
        identity = owner_key(owner(request))
        try:
            return await get_tasks().cancel(identity, task_id)
        except TaskError:
            raise HTTPException(404, "Creation task not found") from None

    async def shutdown():
        if tasks is not None:
            await tasks.close()

    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(instance: FastAPI) -> AsyncIterator[dict[str, Any]]:
        try:
            async with previous_lifespan(instance) as state:
                yield dict(state or {})
        finally:
            await shutdown()

    app.router.lifespan_context = lifespan
