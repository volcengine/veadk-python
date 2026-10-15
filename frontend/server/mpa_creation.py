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

"""Authorized Studio entry points for VeADK-owned MPA creation."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

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
    validate_creation_tos,
    validate_image_reference,
    validate_runtime_name,
    with_creation_images,
    with_creation_resources,
    with_creation_scaling,
    with_creation_tos,
)
from veadk.integrations.mpa.managed.credentials import (
    load_provider_credentials,
    load_volcengine_credentials,
)
from veadk.integrations.mpa.managed.tasks import CreationTasks, TaskError, owner_key
from veadk.integrations.mpa.managed.names import NameCheckError, check_creation_name
from veadk.integrations.mpa.managed.runtime import RuntimeCloud


def creation_agent_id(identity, request_id, explicit=""):
    return (
        explicit
        or "mi-" + uuid5(NAMESPACE_URL, f"veadk:mpa:{identity}:{request_id}").hex[:24]
    )


class NameCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requestId: UUID
    name: str = Field(min_length=4, max_length=64)
    agentId: str = Field(default="", pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    region: str = Field(pattern=r"^(cn-[a-z]+|ap-southeast-1)$", max_length=32)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value):
        return validate_runtime_name(value)


def _studio_task_path(provider="volcengine") -> Path:
    return Path(
        os.getenv(
            "VEADK_MPA_TASK_DB",
            "/tmp/veadk-studio/mpa-creation-byteplus.sqlite3"
            if provider == "byteplus"
            else "/tmp/veadk-studio/mpa-creation.sqlite3",
        )
    )


class CreationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requestId: UUID
    agentId: str = Field(default="", pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    name: str = ""
    description: str = Field(default="", max_length=512)
    maxInstance: int | None = Field(default=None, strict=True, ge=1, le=2**53 - 1)
    region: str = Field(pattern=r"^(cn-[a-z]+|ap-southeast-1)$", max_length=32)
    runtimeImage: str = Field(default="", max_length=1024)
    workerImage: str = Field(default="", max_length=1024)
    pgHost: str = Field(default="", max_length=255)
    pgPort: str = Field(default="", max_length=5)
    openvikingUrl: str = Field(default="", max_length=1024)
    openvikingResourceId: str = Field(default="", max_length=128)
    openvikingApiKey: str = Field(default="", max_length=512, repr=False)
    openvikingMode: Literal["manual", "auto"] = "manual"
    businessWorkspaceMode: Literal["shared", "per-agent"] = "shared"
    businessDatabaseName: Literal["", "aidb"] = ""
    tosBucket: str = Field(default="", max_length=63)

    @field_validator("runtimeImage", "workerImage")
    @classmethod
    def validate_image(cls, value):
        return validate_image_reference(value)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return validate_runtime_name(value)

    @model_validator(mode="after")
    def validate_resources(self):
        if not self.name and not self.agentId:
            raise ValueError("Runtime name is required")
        validate_creation_resources(self.model_dump())
        validate_creation_tos(self.model_dump())
        return self


def mount_mpa_creation_routes(
    app: FastAPI,
    *,
    owner,
    service: CreationTasks | None = None,
    supported=True,
    provider="volcengine",
):
    tasks = service

    def get_tasks():
        nonlocal tasks
        if tasks is None:
            task_path = _studio_task_path(provider)
            tasks = CreationTasks(task_path)
        return tasks

    def profile(region):
        if not supported:
            raise ConfigurationError("MPA creation is unavailable for this provider")
        result = load_studio_profile(region=region, provider=provider)
        try:
            if provider == "volcengine":
                load_volcengine_credentials(result.managed.credential_file)
            else:
                load_provider_credentials(provider, result.managed.credential_file)
        except ValueError:
            raise ConfigurationError(
                "Configure server BytePlus deployment credentials (BYTEPLUS_ACCESS_KEY/BYTEPLUS_SECRET_KEY or VEADK_MPA_BYTEPLUS_CREDENTIAL_FILE)"
                if provider == "byteplus"
                else "Configure server deployment credentials"
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

    async def check_name(body, config, studio_owner, saved_scope=None):
        identity = owner_key(studio_owner)
        agent_id = creation_agent_id(identity, body.requestId)
        if body.agentId and body.agentId != agent_id:
            raise ConfigurationError(
                "New dedicated requests require the server-generated creation identity"
            )
        account = await check_creation_name(
            config,
            RuntimeCloud(
                region=config.region,
                credential_file=config.managed.credential_file,
                provider=provider,
            ),
            agent_id=agent_id,
            name=body.name,
            owner=studio_owner,
            verified_creation_account=(saved_scope or {}).get("account", ""),
        )
        scope = {"provider": provider, "account": account, "region": config.region}
        get_tasks().check_name(
            identity, {"requestId": str(body.requestId), "name": body.name}, scope
        )
        return scope

    @app.post("/web/mpa-creation/name-check")
    async def name_availability(request: Request, body: NameCheckRequest):
        studio_owner = owner(request)
        try:
            _, config = profile(body.region)
            config = with_creation_resources(
                config,
                {"businessWorkspaceMode": "per-agent", "businessDatabaseName": "aidb"},
            )
            await check_name(body, config, studio_owner)
            return {"available": True}
        except NameCheckError as exc:
            raise HTTPException(
                409 if exc.key == "runtimeNameTaken" else 503, {"code": exc.key}
            ) from None
        except ConfigurationError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.post("/web/mpa-creation/tasks", status_code=202)
    async def create(request: Request):
        studio_runtime_owner = owner(request)
        identity = owner_key(studio_runtime_owner)
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
            config = with_creation_scaling(config, body.maxInstance)
            payload = body.model_dump(mode="json")
            if payload["maxInstance"] is None:
                payload.pop("maxInstance")
            if payload["openvikingMode"] == "manual":
                payload.pop("openvikingMode")
            if payload["businessWorkspaceMode"] == "shared":
                payload.pop("businessWorkspaceMode")
            if not payload["businessDatabaseName"]:
                payload.pop("businessDatabaseName")
            if provider == "byteplus":
                payload["provider"] = provider
            if not payload["agentId"]:
                payload["agentId"] = creation_agent_id(identity, body.requestId)
            if not payload["name"]:
                # Keep the exact input shape of already-submitted legacy tasks.
                payload.pop("name")
            tos = {"tosBucket": payload.get("tosBucket", "")}
            if not payload["tosBucket"]:
                payload.pop("tosBucket")
            selected_config = with_creation_resources(config, payload)
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
            with_creation_tos(with_creation_images(config, images), tos)
            name_options = {}
            if body.businessDatabaseName == "aidb":
                saved_scope = get_tasks().name_scope_for_request(identity, payload)
                if saved_scope:
                    get_tasks().check_name(
                        identity,
                        {"requestId": str(body.requestId), "name": body.name},
                        saved_scope,
                    )
                    name_options["name_scope"] = saved_scope
                else:
                    name_options["name_scope"] = await check_name(
                        body, selected_config, studio_runtime_owner
                    )
            return await get_tasks().start(
                identity,
                payload,
                config_path=path,
                timeout=config.managed.timeout_seconds,
                images=images,
                secrets={"openvikingApiKey": openviking_api_key},
                studio_runtime_owner=studio_runtime_owner,
                tos=tos,
                **name_options,
            )
        except NameCheckError as exc:
            raise HTTPException(
                409 if exc.key == "runtimeNameTaken" else 503, {"code": exc.key}
            ) from None
        except ConfigurationError as exc:
            raise HTTPException(400, str(exc)) from None
        except TaskError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.get("/web/mpa-creation/tasks")
    async def list_tasks(
        request: Request, region: str = "", limit: int = 10
    ) -> dict[str, Any]:
        identity = owner_key(owner(request))
        bounded_limit = max(1, min(limit, 50))
        return {
            "tasks": get_tasks().list(
                identity, region=region.strip(), limit=bounded_limit
            )
        }

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
