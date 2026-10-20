# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Admin-only sandbox image inspection and update routes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from veadk.cli.studio_sandbox_updates import SandboxToolUpdates, SandboxUpdateError


def register_sandbox_update_routes(
    app: FastAPI,
    *,
    service: SandboxToolUpdates,
    require_admin: Callable[[Request], None],
    configured_tools: Callable[[], dict[str, str]],
) -> None:
    @app.get("/web/system-info/sandbox-tools/updates")
    async def inspect_updates(request: Request):
        require_admin(request)
        # Codex and DSH aliases resolve to one physical resource.
        tool_ids = set(configured_tools().values()) - {""}

        async def inspect(tool_id: str) -> dict[str, Any]:
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(service.inspect, tool_id), timeout=15
                )
            except TimeoutError:
                return {"toolId": tool_id, "error": "查询沙箱版本超时，请刷新重试"}
            except Exception:
                # SDK errors can include request bodies or credentials. Keep
                # this response separate from the raw control-plane exception.
                return {
                    "toolId": tool_id,
                    "error": "查询沙箱版本失败，请检查凭据、区域及接口权限后重试",
                }

        return {"tools": await asyncio.gather(*(inspect(t) for t in sorted(tool_ids)))}

    @app.post("/web/system-info/sandbox-tools/{kind}/update")
    async def update(request: Request, kind: str):
        require_admin(request)
        tool_id = configured_tools().get(kind)
        if tool_id is None:
            raise HTTPException(status_code=400, detail="Unsupported Sandbox Tool kind")
        if not tool_id:
            raise HTTPException(status_code=400, detail="未配置 Sandbox Tool ID")
        try:
            result = await asyncio.to_thread(service.update, tool_id)
        except (SandboxUpdateError, TimeoutError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(
                status_code=502, detail="Sandbox 更新失败，请刷新检查实际状态及接口权限"
            ) from error
        return {"kind": kind, "toolId": tool_id, **result}
