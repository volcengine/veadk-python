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

"""Server-side executors for tools declared by the Studio frontend."""

from __future__ import annotations

import base64
import inspect
import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from veadk.consts import (
    DEFAULT_IMAGE_EDIT_MODEL_API_BASE,
    DEFAULT_IMAGE_EDIT_MODEL_NAME,
    DEFAULT_IMAGE_GENERATE_MODEL_API_BASE,
    DEFAULT_IMAGE_GENERATE_MODEL_NAME,
    DEFAULT_VIDEO_MODEL_API_BASE,
    DEFAULT_VIDEO_MODEL_NAME,
)
from veadk.version import VERSION

CLIENT_TOOL_NAMES = (
    "ppt_generate",
    "image_generate",
    "image_edit",
    "video_generate",
    "video_task_query",
)

Authorize = Callable[[Request], Any]
CredentialResolver = Callable[[], tuple[str, str, str | None]]


class ClientToolExecuteRequest(BaseModel):
    """One frontend-owned tool execution request."""

    model_config = ConfigDict(extra="forbid")

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


async def _authorize(authorize: Authorize, request: Request) -> None:
    result = authorize(request)
    if inspect.isawaitable(result):
        await result


def _region_for_host(host: str) -> str:
    if "ap-southeast" in host:
        return os.getenv("BYTEPLUS_REGION", "ap-southeast-1")
    return os.getenv("VOLCENGINE_REGION", "cn-beijing")


def _signed_headers(
    method: str,
    url: str,
    body: str,
    credentials: tuple[str, str, str | None],
) -> dict[str, str]:
    """Sign an Ark REST request with the Studio server's IAM credentials."""

    from volcengine.Credentials import Credentials
    from volcengine.auth.SignerV4 import SignerV4
    from volcengine.base.Request import Request as VolcengineRequest

    parsed = urlsplit(url)
    request = VolcengineRequest()
    request.schema = parsed.scheme
    request.method = method
    request.host = parsed.netloc
    request.path = parsed.path
    request.body = body
    request.headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Host": parsed.netloc,
        "User-Agent": f"VeADK/{VERSION}",
        "veadk-source": "veadk",
        "veadk-version": VERSION,
    }
    access_key, secret_key, session_token = credentials
    SignerV4.sign(
        request,
        Credentials(
            access_key,
            secret_key,
            "ark",
            _region_for_host(parsed.netloc),
            session_token or "",
        ),
    )
    return dict(request.headers)


async def _request_json(
    method: str,
    url: str,
    *,
    credentials: tuple[str, str, str | None],
    body: dict[str, Any] | None = None,
    timeout: float = 600,
) -> dict[str, Any]:
    encoded = (
        json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        if body is not None
        else ""
    )
    headers = _signed_headers(method, url, encoded, credentials)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method,
            url,
            headers=headers,
            content=encoded.encode() if encoded else None,
        )
    if response.status_code >= 400:
        detail = response.text.strip()
        raise HTTPException(
            status_code=502,
            detail=f"客户端工具上游请求失败 ({response.status_code})"
            + (f"：{detail[:1000]}" if detail else ""),
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="客户端工具上游返回了无效响应")
    return payload


def _image_request_body(item: dict[str, Any], model_name: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model_name,
        "prompt": item.get("prompt", ""),
    }
    for key in (
        "size",
        "response_format",
        "watermark",
        "image",
        "sequential_image_generation",
        "tools",
        "output_format",
    ):
        if key in item and item[key] is not None:
            body[key] = item[key]
    if (
        item.get("max_images") is not None
        and item.get("sequential_image_generation") == "auto"
    ):
        body["sequential_image_generation_options"] = {"max_images": item["max_images"]}
    return body


def _video_content(item: dict[str, Any]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {"type": "text", "text": str(item.get("prompt", ""))}
    ]
    for key, content_type, role in (
        ("first_frame", "image_url", "first_frame"),
        ("last_frame", "image_url", "last_frame"),
    ):
        if value := item.get(key):
            content.append(
                {
                    "type": content_type,
                    content_type: {"url": value},
                    "role": role,
                }
            )
    for key, content_type, role in (
        ("reference_images", "image_url", "reference_image"),
        ("reference_videos", "video_url", "reference_video"),
        ("reference_audios", "audio_url", "reference_audio"),
    ):
        for value in item.get(key) or []:
            content.append(
                {
                    "type": content_type,
                    content_type: {"url": value},
                    "role": role,
                }
            )
    return content


def _video_request_body(item: dict[str, Any], model_name: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model_name,
        "content": _video_content(item),
    }
    for key in (
        "generate_audio",
        "ratio",
        "duration",
        "resolution",
        "frames",
        "camera_fixed",
        "seed",
        "watermark",
        "tools",
    ):
        if key in item and item[key] is not None:
            body[key] = item[key]
    return body


async def _ppt_generate(arguments: dict[str, Any]) -> dict[str, Any]:
    from veadk.tools.builtin_tools.ppt_generate import (
        PPTX_MIME_TYPE,
        _clean_text,
        _create_pptx,
        _parse_deck_markdown,
        _safe_filename,
    )

    title = _clean_text(arguments.get("title"), 160)
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    slides = _parse_deck_markdown(str(arguments.get("deck_markdown") or ""))
    if not slides:
        raise HTTPException(
            status_code=400,
            detail="deck_markdown must contain a slide starting with ##",
        )
    filename = _safe_filename(str(arguments.get("filename") or ""), title)
    theme = str(arguments.get("theme") or "blue")
    spec: dict[str, object] = {
        "title": title,
        "subtitle": _clean_text(arguments.get("subtitle"), 240),
        "theme": theme if theme in {"blue", "dark", "warm", "green"} else "blue",
        "slides": slides,
    }
    with tempfile.TemporaryDirectory(prefix="veadk-studio-ppt-") as temp_dir:
        output = Path(temp_dir) / filename
        preview = Path(temp_dir) / f"{Path(filename).stem}.preview.webp"
        await _create_pptx(spec, output, preview)
        encoded = base64.b64encode(output.read_bytes()).decode()
    return {
        "result": {
            "status": "created",
            "filename": filename,
            "slide_count": len(slides) + 1,
        },
        "downloads": [
            {
                "filename": filename,
                "mimeType": PPTX_MIME_TYPE,
                "data": encoded,
            }
        ],
    }


async def _image_generate(
    arguments: dict[str, Any],
    credentials: tuple[str, str, str | None],
) -> dict[str, Any]:
    tasks = arguments.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise HTTPException(status_code=400, detail="tasks is required")
    model_name = str(
        arguments.get("model_name")
        or os.getenv("MODEL_IMAGE_NAME")
        or DEFAULT_IMAGE_GENERATE_MODEL_NAME
    )
    base_url = os.getenv(
        "MODEL_IMAGE_API_BASE", DEFAULT_IMAGE_GENERATE_MODEL_API_BASE
    ).rstrip("/")
    timeout = float(arguments.get("timeout") or 600)
    results = [
        await _request_json(
            "POST",
            f"{base_url}/images/generations",
            credentials=credentials,
            body=_image_request_body(item, model_name),
            timeout=timeout,
        )
        for item in tasks
        if isinstance(item, dict)
    ]
    return {"result": {"status": "completed", "results": results}}


async def _image_edit(
    arguments: dict[str, Any],
    credentials: tuple[str, str, str | None],
) -> dict[str, Any]:
    params = arguments.get("params")
    if not isinstance(params, list) or not params:
        raise HTTPException(status_code=400, detail="params is required")
    base_url = os.getenv(
        "MODEL_EDIT_API_BASE", DEFAULT_IMAGE_EDIT_MODEL_API_BASE
    ).rstrip("/")
    model_name = os.getenv("MODEL_EDIT_NAME", DEFAULT_IMAGE_EDIT_MODEL_NAME)
    results = []
    for item in params:
        if not isinstance(item, dict):
            continue
        body = {
            "model": model_name,
            "prompt": item.get("prompt", ""),
            "image": item.get("origin_image", ""),
        }
        for key in ("response_format", "guidance_scale", "watermark", "seed"):
            if key in item and item[key] is not None:
                body[key] = item[key]
        results.append(
            await _request_json(
                "POST",
                f"{base_url}/images/generations",
                credentials=credentials,
                body=body,
            )
        )
    return {"result": {"status": "completed", "results": results}}


async def _video_generate(
    arguments: dict[str, Any],
    credentials: tuple[str, str, str | None],
) -> dict[str, Any]:
    params = arguments.get("params")
    if not isinstance(params, list) or not params:
        raise HTTPException(status_code=400, detail="params is required")
    base_url = os.getenv("MODEL_VIDEO_API_BASE", DEFAULT_VIDEO_MODEL_API_BASE).rstrip(
        "/"
    )
    model_name = str(
        arguments.get("model_name")
        or os.getenv("MODEL_VIDEO_NAME")
        or DEFAULT_VIDEO_MODEL_NAME
    )
    pending = []
    for index, item in enumerate(params):
        if not isinstance(item, dict):
            continue
        response = await _request_json(
            "POST",
            f"{base_url}/contents/generations/tasks",
            credentials=credentials,
            body=_video_request_body(item, model_name),
            timeout=120,
        )
        pending.append(
            {
                "video_name": item.get("video_name", f"generated_video_{index}"),
                "task_id": response.get("id") or response.get("task_id"),
                "status": response.get("status", "pending"),
            }
        )
    return {
        "result": {
            "status": "pending",
            "success_list": [],
            "error_list": [],
            "pending_list": pending,
        }
    }


async def _video_task_query(
    arguments: dict[str, Any],
    credentials: tuple[str, str, str | None],
) -> dict[str, Any]:
    task_id = str(arguments.get("task_id") or "").strip()
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id is required")
    base_url = os.getenv("MODEL_VIDEO_API_BASE", DEFAULT_VIDEO_MODEL_API_BASE).rstrip(
        "/"
    )
    response = await _request_json(
        "GET",
        f"{base_url}/contents/generations/tasks/{task_id}",
        credentials=credentials,
        timeout=120,
    )
    return {"result": response}


async def execute_client_tool(
    name: str,
    arguments: dict[str, Any],
    credentials: CredentialResolver,
) -> dict[str, Any]:
    if name == "ppt_generate":
        return await _ppt_generate(arguments)
    if name not in CLIENT_TOOL_NAMES:
        raise HTTPException(status_code=404, detail=f"Unknown client tool: {name}")
    resolved = credentials()
    if name == "image_generate":
        return await _image_generate(arguments, resolved)
    if name == "image_edit":
        return await _image_edit(arguments, resolved)
    if name == "video_generate":
        return await _video_generate(arguments, resolved)
    if name == "video_task_query":
        return await _video_task_query(arguments, resolved)
    raise AssertionError(f"Unhandled client tool: {name}")


def mount_frontend_client_tool_routes(
    app: FastAPI,
    *,
    authorize: Authorize,
    credentials: CredentialResolver,
) -> None:
    """Mount Studio-owned client tool capability and execution routes."""

    @app.get("/web/client-tools/capabilities")
    async def client_tool_capabilities(request: Request) -> dict[str, object]:
        await _authorize(authorize, request)
        return {
            "protocols": {"client_tools": {"version": 1}},
            "tools": list(CLIENT_TOOL_NAMES),
        }

    @app.post("/web/client-tools/execute")
    async def run_client_tool(
        payload: ClientToolExecuteRequest,
        request: Request,
    ) -> dict[str, Any]:
        await _authorize(authorize, request)
        return await execute_client_tool(payload.name, payload.arguments, credentials)


__all__ = [
    "CLIENT_TOOL_NAMES",
    "execute_client_tool",
    "mount_frontend_client_tool_routes",
]
