# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""AgentKit Runtime transport for website chat."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
from fastapi import HTTPException, Response
from fastapi.responses import StreamingResponse

from veadk.utils.logger import get_logger

from .models import WebsiteIntegration

logger = get_logger(__name__)

RuntimeGetter = Callable[[str, str], Any]
RuntimeConnectionResolver = Callable[[str, str, Any | None], tuple[str, str, str, str]]
ProxyHeaderBuilder = Callable[[dict[str, str], str | None, str | None], dict[str, str]]


async def invoke_agentkit_runtime(
    integration: WebsiteIntegration,
    payload: dict[str, Any],
    *,
    get_runtime: RuntimeGetter,
    resolve_connection: RuntimeConnectionResolver,
    build_headers: ProxyHeaderBuilder,
) -> Response:
    try:
        runtime = get_runtime(integration.runtime_id, integration.region)
        endpoint, api_key, auth_type, _ = resolve_connection(
            integration.runtime_id,
            integration.region,
            runtime,
        )
    except HTTPException:
        raise
    except Exception as error:
        logger.exception(
            "website integration runtime resolution failed runtime_id=%s",
            integration.runtime_id,
        )
        raise HTTPException(
            status_code=502,
            detail="无法连接 Runtime，请稍后重试。",
        ) from error
    if auth_type == "custom_jwt":
        raise HTTPException(
            status_code=400,
            detail="网站集成暂不支持使用自定义 JWT 鉴权的 Runtime。",
        )

    headers = build_headers(
        {
            "accept": "text/event-stream",
            "content-type": "application/json",
        },
        api_key,
        None,
    )
    client = httpx.AsyncClient(timeout=None)
    request = client.build_request(
        "POST",
        f"{endpoint.rstrip('/')}/run_sse",
        headers=headers,
        content=json.dumps(payload).encode("utf-8"),
    )
    try:
        upstream = await client.send(request, stream=True)
    except httpx.HTTPError as error:
        await client.aclose()
        logger.exception(
            "website integration Runtime request failed runtime_id=%s",
            integration.runtime_id,
        )
        raise HTTPException(
            status_code=502,
            detail="Runtime 请求失败，请稍后重试。",
        ) from error

    media_type = upstream.headers.get("content-type", "text/event-stream")
    if upstream.status_code >= 400:
        content = await upstream.aread()
        await upstream.aclose()
        await client.aclose()
        return Response(
            content=content,
            status_code=upstream.status_code,
            media_type=media_type,
        )

    async def stream():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        stream(),
        status_code=upstream.status_code,
        media_type=media_type,
    )
