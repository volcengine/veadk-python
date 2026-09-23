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

"""Authorized quality endpoints, independent of existing evaluation storage."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel

from .models import (
    ComponentGenerationRequest,
    ComponentPreferences,
    EvaluationBrief,
    GeneratedDataset,
    GeneratedEvaluators,
    GenerateRequest,
    QualityRequest,
    PreferencesRequest,
    PreferenceSuggestions,
    PreferenceSuggestionsRequest,
)
from .service import QualityGenerationService, dataset_generation_timeout
from .errors import QualityGenerationError, generation_diagnostics


def mount_quality_routes(
    app: Any,
    *,
    provider: str,
    resolve_api_key: Callable[[], str],
    authorize: Callable[[Request], Any],
    authorize_runtime: Callable[[Request, str, str], Any],
) -> None:
    service = QualityGenerationService(provider, resolve_api_key)

    async def run(
        request: Request,
        body: QualityRequest,
        operation: Callable[[], Awaitable[BaseModel]],
        timeout: int = 180,
    ) -> BaseModel:
        authorize(request)
        if body.runtimeId:
            if not body.region:
                raise HTTPException(status_code=422, detail="quality_region_required")
            await asyncio.to_thread(
                authorize_runtime, request, body.runtimeId, body.region
            )

        async def execute() -> BaseModel:
            if not isinstance(body, GenerateRequest):
                return await operation()

            async def disconnected() -> None:
                while not await request.is_disconnected():
                    await asyncio.sleep(0.5)

            generation = asyncio.ensure_future(operation())
            disconnect = asyncio.create_task(disconnected())
            try:
                done, _ = await asyncio.wait(
                    [generation, disconnect], return_when=asyncio.FIRST_COMPLETED
                )
                if generation in done:
                    return generation.result()
                raise HTTPException(
                    status_code=499, detail="quality_generation_cancelled"
                )
            finally:
                generation.cancel()
                disconnect.cancel()
                await asyncio.gather(generation, disconnect, return_exceptions=True)

        try:
            return await asyncio.wait_for(execute(), timeout=timeout)
        except HTTPException:
            raise
        except QualityGenerationError as error:
            raise HTTPException(
                status_code=504 if error.timeout else 502,
                detail={"code": str(error), "diagnostics": error.diagnostics},
            ) from error
        except (TimeoutError, asyncio.TimeoutError) as error:
            raise HTTPException(
                status_code=504,
                detail={
                    "code": "quality_generation_timeout",
                    "diagnostics": generation_diagnostics(error),
                },
            ) from error
        except Exception as error:
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "quality_generation_failed",
                    "diagnostics": generation_diagnostics(error),
                },
            ) from error

    @app.post("/web/quality/autofill", response_model=EvaluationBrief)
    async def autofill(request: Request, body: QualityRequest) -> BaseModel:
        return await run(request, body, lambda: service.autofill(body))

    @app.post("/web/quality/generate", response_model=GeneratedDataset)
    async def generate(request: Request, body: GenerateRequest) -> BaseModel:
        return await run(
            request,
            body,
            lambda: service.generate(body),
            dataset_generation_timeout(body.count),
        )

    @app.post("/web/quality/evaluators", response_model=GeneratedEvaluators)
    async def generate_evaluators(
        request: Request, body: ComponentGenerationRequest
    ) -> BaseModel:
        return await run(request, body, lambda: service.generate_evaluators(body))

    @app.post("/web/quality/preferences", response_model=ComponentPreferences)
    async def generate_preferences(
        request: Request, body: PreferencesRequest
    ) -> BaseModel:
        return await run(request, body, lambda: service.generate_preferences(body))

    @app.post(
        "/web/quality/preference-suggestions", response_model=PreferenceSuggestions
    )
    async def suggest_preferences(
        request: Request, body: PreferenceSuggestionsRequest
    ) -> BaseModel:
        return await run(request, body, lambda: service.suggest_preferences(body))
