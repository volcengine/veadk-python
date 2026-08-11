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

"""FastAPI transport for Studio video creation."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from .client import (
    ArkHttpClient,
    ArkPromptClient,
    ArkServiceError,
    ArkTokenCache,
    ArkTokenProvider,
    ArkVideoClient,
    CredentialResolver,
)
from .models import (
    PromptEnhanceRequest,
    PromptEnhanceResponse,
    VideoAssetResponse,
    VideoAssetRole,
    VideoCapabilities,
    VideoProviderConfig,
    VideoTaskCreateRequest,
    VideoTaskResponse,
)
from .service import (
    VideoInputError,
    VideoService,
    VideoTaskAccessDenied,
    VideoTaskNotFound,
)
from .storage import (
    LazyVideoAssetRepository,
    VideoAssetNotFound,
    VideoAssetStorageUnavailable,
    video_asset_repository_factory,
)

IdentityResolver = Callable[[Request], str]

_PROVIDER_DEFAULTS = {
    "volcengine": {
        "region": "cn-beijing",
        "api_base": "https://ark.cn-beijing.volces.com/api/v3",
        "generation_model": "doubao-seedance-2-5-260628",
        "enhancer_model": "doubao-seed-2-1-pro-260628",
    },
    "byteplus": {
        "region": "ap-southeast-1",
        "api_base": "https://ark.ap-southeast.bytepluses.com/api/v3",
        "generation_model": "dreamina-seedance-2-5-260628",
        "enhancer_model": "dola-seed-2-1-turbo-260628",
    },
}


def build_video_service(
    *,
    provider: Literal["volcengine", "byteplus"],
    resolve_credentials: CredentialResolver,
    http_client: httpx.AsyncClient | None = None,
    token_loader: Callable[..., str] | None = None,
) -> VideoService:
    """Compose production dependencies while keeping each layer testable."""
    if provider not in _PROVIDER_DEFAULTS:
        raise ValueError(f"Unsupported video provider: {provider}")
    defaults = _PROVIDER_DEFAULTS[provider]
    config = VideoProviderConfig(
        provider=provider,
        region=str(defaults["region"]),
        api_base=str(defaults["api_base"]),
        generation_model=str(defaults["generation_model"]),
        enhancer_model=str(defaults["enhancer_model"]),
    )
    if token_loader is None:
        token_cache = ArkTokenCache(
            provider=provider,
            region=config.region,
            resolve_credentials=resolve_credentials,
            api_key_name=os.getenv("MODEL_AGENT_API_KEY_NAME") or None,
        )
    else:
        token_cache = ArkTokenCache(
            provider=provider,
            region=config.region,
            resolve_credentials=resolve_credentials,
            api_key_name=os.getenv("MODEL_AGENT_API_KEY_NAME") or None,
            token_loader=token_loader,
        )
    prompt_token = ArkTokenProvider(
        token_cache,
        os.getenv("MODEL_AGENT_API_KEY", ""),
    )
    video_token = ArkTokenProvider(
        token_cache,
        os.getenv("MODEL_VIDEO_API_KEY") or os.getenv("MODEL_AGENT_API_KEY", ""),
    )
    prompt_transport = ArkHttpClient(
        provider=provider,
        api_base=os.getenv("MODEL_AGENT_API_BASE", config.api_base),
        token_provider=prompt_token,
        http_client=http_client,
    )
    video_transport = ArkHttpClient(
        provider=provider,
        api_base=os.getenv("MODEL_VIDEO_API_BASE", config.api_base),
        token_provider=video_token,
        http_client=http_client or prompt_transport.http_client,
    )
    asset_factory, max_asset_bytes = video_asset_repository_factory(
        provider=provider,
        resolve_credentials=resolve_credentials,
    )
    return VideoService(
        config=config,
        prompt_client=ArkPromptClient(config=config, transport=prompt_transport),
        video_client=ArkVideoClient(config=config, transport=video_transport),
        assets=LazyVideoAssetRepository(asset_factory),
        max_asset_bytes=max_asset_bytes,
    )


def mount_video_routes(
    app: FastAPI,
    *,
    service: VideoService,
    identity_resolver: IdentityResolver,
) -> None:
    @app.get(
        "/web/video/capabilities",
        response_model=VideoCapabilities,
        response_model_by_alias=True,
    )
    async def capabilities() -> VideoCapabilities:
        return service.capabilities()

    @app.post(
        "/web/video/assets",
        response_model=VideoAssetResponse,
        response_model_by_alias=True,
    )
    async def upload_asset(
        request: Request,
        role: Annotated[VideoAssetRole, Form()],
        file: Annotated[UploadFile, File()],
    ) -> VideoAssetResponse:
        owner_id = identity_resolver(request)
        suffix = Path(file.filename or "asset").suffix
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
                temp_path = Path(temp.name)
                size_bytes = 0
                while chunk := await file.read(1024 * 1024):
                    size_bytes += len(chunk)
                    if size_bytes > service.max_asset_bytes:
                        limit_mb = service.max_asset_bytes // (1024 * 1024)
                        raise HTTPException(
                            status_code=413,
                            detail=f"素材超过 {limit_mb} MB 上传限制。",
                        )
                    temp.write(chunk)
            return await service.upload_asset(
                owner_id=owner_id,
                role=role,
                file_name=file.filename or "asset",
                declared_mime_type=file.content_type or "",
                source=temp_path,
            )
        except VideoAssetStorageUnavailable as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        finally:
            await file.close()
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    @app.post(
        "/web/video/prompts/enhance",
        response_model=PromptEnhanceResponse,
        response_model_by_alias=True,
    )
    async def enhance_prompt(
        body: PromptEnhanceRequest,
        request: Request,
    ) -> PromptEnhanceResponse:
        owner_id = identity_resolver(request)
        try:
            return await service.enhance_prompt(owner_id, body)
        except Exception as error:
            _raise_api_error(error)
            raise

    @app.post(
        "/web/video/tasks",
        status_code=202,
        response_model=VideoTaskResponse,
        response_model_by_alias=True,
    )
    async def create_task(
        body: VideoTaskCreateRequest,
        request: Request,
    ) -> VideoTaskResponse:
        owner_id = identity_resolver(request)
        try:
            return await service.create_task(owner_id, body)
        except Exception as error:
            _raise_api_error(error)
            raise

    @app.get(
        "/web/video/tasks/{task_id}",
        response_model=VideoTaskResponse,
        response_model_by_alias=True,
    )
    async def get_task(task_id: str, request: Request) -> VideoTaskResponse:
        owner_id = identity_resolver(request)
        try:
            return await service.get_task(owner_id, task_id)
        except Exception as error:
            _raise_api_error(error)
            raise

    @app.get("/web/video/tasks/{task_id}/download")
    async def download_task(task_id: str, request: Request) -> StreamingResponse:
        owner_id = identity_resolver(request)
        try:
            response, output_format = await service.open_download(owner_id, task_id)
        except Exception as error:
            _raise_api_error(error)
            raise
        headers = {
            "Content-Disposition": (f'attachment; filename="video.{output_format}"')
        }
        if content_length := response.headers.get("content-length"):
            headers["Content-Length"] = content_length
        return StreamingResponse(
            response.aiter_bytes(),
            media_type=response.headers.get("content-type", "video/mp4"),
            headers=headers,
            background=BackgroundTask(response.aclose),
        )


def _raise_api_error(error: Exception) -> None:
    if isinstance(error, (VideoTaskNotFound, VideoAssetNotFound)):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(error, VideoTaskAccessDenied):
        raise HTTPException(status_code=403, detail=str(error)) from error
    if isinstance(error, (VideoInputError, ValueError)):
        raise HTTPException(status_code=400, detail=str(error)) from error
    if isinstance(error, VideoAssetStorageUnavailable):
        raise HTTPException(status_code=503, detail=str(error)) from error
    if isinstance(error, ArkServiceError):
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


__all__ = ["build_video_service", "mount_video_routes"]
