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

import asyncio
import json
import subprocess
from types import SimpleNamespace
from typing import Literal

import httpx
import pytest
from fastapi import FastAPI, Request

from frontend.server.video.client import (
    ArkHttpClient,
    ArkPromptClient,
    ArkServiceError,
    ArkTokenCache,
    ArkTokenProvider,
)
from frontend.server.video.prompts import parameter_policy
from frontend.server.video.routes import build_video_service, mount_video_routes
from frontend.server.video.service import VideoInputError, VideoService
from frontend.server.video.storage import VideoAssetRepository
from veadk.multimodal.service import MediaService


def _enhancer_output() -> str:
    return json.dumps(
        {
            "task_type": "text_to_video",
            "lock_mode": "unlocked",
            "intent_confidence": 0.98,
            "reasoning_summary": "The request describes a new scene without assets.",
            "enhanced_prompt": "A cinematic sunrise over a quiet mountain lake.",
            "asset_mapping": [],
            "param_policy": parameter_policy("text_to_video"),
            "risk_flags": [],
            "rewrite_notes": ["Added camera and lighting detail."],
        }
    )


@pytest.mark.asyncio
async def test_reference_video_pixel_validation_is_returned_as_bad_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def probe(*args, **kwargs) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=json.dumps({"streams": [{"width": 640, "height": 360}]}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", probe)
    repository = VideoAssetRepository(
        MediaService(  # type: ignore[arg-type]
            SimpleNamespace(),
            max_file_bytes=1024 * 1024,
        )
    )
    service = SimpleNamespace(
        max_asset_bytes=1024 * 1024,
        upload_asset=repository.save,
    )
    app = FastAPI()
    mount_video_routes(
        app,
        service=service,  # type: ignore[arg-type]
        identity_resolver=lambda _: "alice",
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/web/video/assets",
            data={"role": "reference_video"},
            files={"file": ("reference.mp4", b"video-bytes", "video/mp4")},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "参考视频分辨率过低（640×360）。"
        "Seedance 2.5 要求参考视频至少包含 409600 个像素，例如 854×480。"
    )


@pytest.mark.asyncio
async def test_text_to_video_route_flow_and_owner_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_AGENT_API_KEY", "test-model-key")
    monkeypatch.delenv("MODEL_VIDEO_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_AGENT_NAME", raising=False)
    monkeypatch.delenv("MODEL_VIDEO_NAME", raising=False)
    monkeypatch.setenv("VEADK_VIDEO_ASSET_STORAGE", "local")
    seen_requests: list[httpx.Request] = []
    task_status = {"value": "succeeded"}

    def upstream(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        if request.url == httpx.URL("https://cdn.example/video.mp4"):
            assert "authorization" not in request.headers
            return httpx.Response(
                200,
                content=b"video-bytes",
                headers={"content-type": "video/mp4"},
            )
        assert request.headers["authorization"] == "Bearer test-model-key"
        if request.url.path.endswith("/responses"):
            assert json.loads(request.content) == {
                "model": "doubao-seed-2-1-pro-260628",
                "input": [
                    {
                        "role": "system",
                        "content": json.loads(request.content)["input"][0]["content"],
                    },
                    {
                        "role": "user",
                        "content": json.loads(request.content)["input"][1]["content"],
                    },
                ],
                "thinking": {"type": "disabled"},
            }
            return httpx.Response(
                200,
                json={"output_text": _enhancer_output()},
            )
        if request.method == "POST" and request.url.path.endswith(
            "/contents/generations/tasks"
        ):
            body = json.loads(request.content)
            assert body == {
                "model": "doubao-seedance-2-5-260628",
                "content": [
                    {
                        "type": "text",
                        "text": "A cinematic sunrise over a quiet mountain lake.",
                    }
                ],
                "ratio": "16:9",
                "resolution": "720p",
                "duration": 8,
                "output_format": "mp4",
                "generate_audio": True,
            }
            return httpx.Response(200, json={"id": "cgt-test"})
        if request.method == "GET" and request.url.path.endswith(
            "/contents/generations/tasks/cgt-test"
        ):
            if task_status["value"] == "expired":
                return httpx.Response(200, json={"status": "expired"})
            return httpx.Response(
                200,
                json={
                    "status": "succeeded",
                    "content": {"video_url": "https://cdn.example/video.mp4"},
                },
            )
        raise AssertionError(
            f"Unexpected upstream request: {request.method} {request.url}"
        )

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    service = build_video_service(
        provider="volcengine",
        resolve_credentials=lambda: (_ for _ in ()).throw(
            AssertionError("AK/SK lookup is unnecessary with an explicit model key")
        ),
        http_client=upstream_client,
    )
    app = FastAPI()

    def identity(request: Request) -> str:
        return request.headers.get("x-test-user", "alice")

    mount_video_routes(app, service=service, identity_resolver=identity)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"x-test-user": "alice"},
    )
    try:
        capabilities = (await client.get("/web/video/capabilities")).json()
        assert capabilities["provider"] == "volcengine"
        assert capabilities["assetStorageAvailable"] is False
        assert capabilities["assetStorageUnavailableReason"] == (
            "管理员未配置持久化存储"
        )

        unavailable_upload = await client.post(
            "/web/video/assets",
            data={"role": "reference_image"},
            files={"file": ("reference.png", b"not-used", "image/png")},
        )
        assert unavailable_upload.status_code == 503
        assert unavailable_upload.json()["detail"] == "管理员未配置持久化存储"

        enhance_response = await client.post(
            "/web/video/prompts/enhance",
            json={"prompt": "湖边日出", "taskMode": "auto"},
        )
        assert enhance_response.status_code == 200
        enhanced = enhance_response.json()
        assert enhanced["resolvedTaskMode"] == "text_to_video"
        assert enhanced["enhancerModel"] == "doubao-seed-2-1-pro-260628"

        create_response = await client.post(
            "/web/video/tasks",
            json={
                "enhancedPrompt": enhanced["enhancedPrompt"],
                "resolvedTaskMode": enhanced["resolvedTaskMode"],
                "ratio": enhanced["ratio"],
                "resolution": enhanced["resolution"],
                "durationSeconds": enhanced["durationSeconds"],
            },
        )
        assert create_response.status_code == 202
        assert create_response.json()["taskId"] == "cgt-test"
        assert create_response.json()["outputFormat"] == "mp4"

        denied = await client.get(
            "/web/video/tasks/cgt-test",
            headers={"x-test-user": "bob"},
        )
        assert denied.status_code == 403

        status_response = await client.get("/web/video/tasks/cgt-test")
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "succeeded"
        assert status_response.json()["videoUrl"] == "https://cdn.example/video.mp4"

        download_response = await client.get("/web/video/tasks/cgt-test/download")
        assert download_response.status_code == 200
        assert download_response.content == b"video-bytes"
        assert download_response.headers["content-disposition"] == (
            'attachment; filename="video.mp4"'
        )

        task_status["value"] = "expired"
        expired_response = await client.get("/web/video/tasks/cgt-test")
        assert expired_response.status_code == 200
        assert expired_response.json()["status"] == "failed"
        assert "已过期" in expired_response.json()["error"]
        assert len(seen_requests) == 5
    finally:
        await client.aclose()
        await upstream_client.aclose()


@pytest.mark.asyncio
async def test_token_cache_deduplicates_concurrent_iam_resolution() -> None:
    calls = 0

    def load_token(*args, **kwargs) -> str:
        nonlocal calls
        calls += 1
        return f"token-{calls}"

    cache = ArkTokenCache(
        provider="volcengine",
        region="cn-beijing",
        resolve_credentials=lambda: ("ak", "sk", "sts"),
        token_loader=load_token,
        ttl_seconds=60,
    )

    first = await asyncio.gather(*(cache.get() for _ in range(8)))
    assert first == ["token-1"] * 8
    assert calls == 1
    assert await cache.get(force_refresh=True) == "token-2"
    assert calls == 2


@pytest.mark.asyncio
async def test_ark_transport_refreshes_cached_token_once_after_401() -> None:
    loaded = 0
    authorizations: list[str] = []

    def load_token(*args, **kwargs) -> str:
        nonlocal loaded
        loaded += 1
        return f"token-{loaded}"

    def upstream(request: httpx.Request) -> httpx.Response:
        authorizations.append(request.headers["authorization"])
        if len(authorizations) == 1:
            return httpx.Response(401, json={"error": "expired"})
        return httpx.Response(200, json={"ok": True})

    cache = ArkTokenCache(
        provider="volcengine",
        region="cn-beijing",
        resolve_credentials=lambda: ("ak", "sk", None),
        token_loader=load_token,
    )
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    transport = ArkHttpClient(
        provider="volcengine",
        api_base="https://ark.example/api/v3",
        token_provider=ArkTokenProvider(cache),
        http_client=http_client,
    )
    try:
        response = await transport.request("GET", "/test")
        assert response.status_code == 200
        assert authorizations == ["Bearer token-1", "Bearer token-2"]
        assert loaded == 2
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "model", "console_name"),
    [
        ("volcengine", "doubao-seedance-2-5-260628", "方舟控制台"),
        ("byteplus", "dreamina-seedance-2-5-260628", "ModelArk 控制台"),
    ],
)
async def test_model_not_open_error_names_model_and_recovery_console(
    provider: Literal["volcengine", "byteplus"],
    model: str,
    console_name: str,
) -> None:
    def upstream(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "error": {
                    "code": "ModelNotOpen",
                    "message": f"Account has not activated model {model}.",
                }
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    cache = ArkTokenCache(
        provider=provider,
        region="cn-beijing",
        resolve_credentials=lambda: ("ak", "sk", None),
        token_loader=lambda *args, **kwargs: "token",
    )
    transport = ArkHttpClient(
        provider=provider,
        api_base="https://ark.example/api/v3",
        token_provider=ArkTokenProvider(cache),
        http_client=http_client,
    )
    try:
        with pytest.raises(ArkServiceError) as raised:
            await transport.request(
                "POST", "/contents/generations/tasks", json={"model": model}
            )
        message = str(raised.value)
        assert model in message
        assert console_name in message
        assert "HTTP 404" not in message
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("upstream_message", "expected_message"),
    [
        (
            (
                "the parameter duration specified in the request is not valid "
                "for model doubao-seedance-2-5 Request id: secret-request-id"
            ),
            "视频时长不受当前模型支持，请选择 4 至 30 秒。",
        ),
        (
            "invalid image URL https://assets.example/private?signature=secret",
            "视频生成参数无效，请检查当前任务配置。",
        ),
    ],
)
async def test_invalid_parameter_error_is_specific_without_leaking_values(
    upstream_message: str,
    expected_message: str,
) -> None:
    def upstream(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "code": "InvalidParameter",
                    "message": upstream_message,
                }
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    cache = ArkTokenCache(
        provider="volcengine",
        region="cn-beijing",
        resolve_credentials=lambda: ("ak", "sk", None),
        token_loader=lambda *args, **kwargs: "token",
    )
    transport = ArkHttpClient(
        provider="volcengine",
        api_base="https://ark.example/api/v3",
        token_provider=ArkTokenProvider(cache),
        http_client=http_client,
    )
    try:
        with pytest.raises(ArkServiceError) as raised:
            await transport.request("POST", "/contents/generations/tasks", json={})
        assert raised.value.status_code == 400
        assert str(raised.value) == expected_message
        assert "secret" not in str(raised.value)
    finally:
        await http_client.aclose()


def test_responses_api_nested_output_text_is_supported() -> None:
    assert (
        ArkPromptClient._response_text(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "reasoning", "text": "do not expose this"},
                            {"type": "output_text", "text": "  enhanced JSON  "},
                        ],
                    }
                ]
            }
        )
        == "enhanced JSON"
    )


def test_asset_roles_and_model_mapping_are_strictly_validated() -> None:
    reference_image = SimpleNamespace(role="reference_image")
    reference_video = SimpleNamespace(role="reference_video")
    first_frame = SimpleNamespace(role="first_frame")

    VideoService._validate_assets(
        "reference_to_video",
        [reference_image, reference_video],  # type: ignore[list-item]
    )
    VideoService._validate_assets(
        "first_last_frame",
        [first_frame],  # type: ignore[list-item]
    )
    with pytest.raises(VideoInputError, match="参考视频"):
        VideoService._validate_assets(
            "video_editing",
            [reference_image],  # type: ignore[list-item]
        )
    with pytest.raises(VideoInputError, match="最多上传一个"):
        VideoService._validate_assets(
            "reference_to_video",
            [reference_image, reference_image],  # type: ignore[list-item]
        )
    with pytest.raises(ArkServiceError, match="素材不一致"):
        VideoService._validate_asset_mapping(
            [],
            [reference_image],  # type: ignore[list-item]
        )


@pytest.mark.asyncio
async def test_download_filename_uses_task_output_format() -> None:
    class DownloadOnlyService:
        async def open_download(self, owner_id: str, task_id: str):
            assert owner_id == "alice"
            assert task_id == "mov-task"
            return httpx.Response(200, content=b"mov-bytes"), "mov"

    app = FastAPI()
    mount_video_routes(
        app,
        service=DownloadOnlyService(),  # type: ignore[arg-type]
        identity_resolver=lambda _: "alice",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/web/video/tasks/mov-task/download")

    assert response.status_code == 200
    assert response.content == b"mov-bytes"
    assert response.headers["content-disposition"] == (
        'attachment; filename="video.mov"'
    )


@pytest.mark.asyncio
async def test_byteplus_capabilities_use_native_model_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MODEL_AGENT_NAME", raising=False)
    monkeypatch.delenv("MODEL_VIDEO_NAME", raising=False)
    monkeypatch.setenv("VEADK_VIDEO_ASSET_STORAGE", "local")
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(500))
    )
    try:
        service = build_video_service(
            provider="byteplus",
            resolve_credentials=lambda: ("ak", "sk", None),
            http_client=http_client,
        )
        capabilities = service.capabilities()
        assert capabilities.generation_model == "dreamina-seedance-2-5-260628"
        assert capabilities.enhancer_model == "dola-seed-2-1-turbo-260628"
    finally:
        await http_client.aclose()
