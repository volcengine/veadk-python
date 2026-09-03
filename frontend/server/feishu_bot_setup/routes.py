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

"""FastAPI transport for the reusable Feishu bot setup service."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from .service import (
    FeishuBotSetupNotFound,
    FeishuBotSetupService,
    FeishuBotSetupUnavailable,
)


class CreateFeishuBotSetupBody(BaseModel):
    agent_name: str = Field(alias="agentName", min_length=1, max_length=128)


def mount_feishu_bot_setup_routes(
    app: Any,
    service: FeishuBotSetupService,
    owner_resolver: Callable[[Request], str],
) -> None:
    async def invoke(call: Callable[[], dict[str, object]]) -> dict[str, object]:
        try:
            return await run_in_threadpool(call)
        except FeishuBotSetupUnavailable as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except FeishuBotSetupNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/web/feishu-bot-setup/sessions")
    async def create_session(
        body: CreateFeishuBotSetupBody, request: Request
    ) -> dict[str, object]:
        owner = owner_resolver(request)
        return await invoke(
            lambda: service.create(owner=owner, agent_name=body.agent_name)
        )

    @app.get("/web/feishu-bot-setup/sessions/{session_id}")
    async def get_session(session_id: str, request: Request) -> dict[str, object]:
        owner = owner_resolver(request)
        return await invoke(lambda: service.get(owner=owner, session_id=session_id))

    @app.delete("/web/feishu-bot-setup/sessions/{session_id}")
    async def cancel_session(session_id: str, request: Request) -> dict[str, object]:
        owner = owner_resolver(request)
        return await invoke(lambda: service.cancel(owner=owner, session_id=session_id))
