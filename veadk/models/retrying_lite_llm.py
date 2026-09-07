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

"""A narrowly bounded LiteLLM retry for first-request quota races."""

from __future__ import annotations

import asyncio
import copy
import math
from collections.abc import AsyncGenerator
from typing import Any

from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from typing_extensions import override

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_RETRY_DELAY_SECONDS = 0.5
_MAX_RETRY_DELAY_SECONDS = 2.0


def _status_code(error: BaseException) -> int | None:
    candidates = (
        getattr(error, "status_code", None),
        getattr(getattr(error, "response", None), "status_code", None),
    )
    for value in candidates:
        if value is None:
            continue
        try:
            code = int(value)
        except (TypeError, ValueError):
            continue
        if code == 429:
            return code
    return None


def _retry_delay_seconds(error: BaseException) -> float:
    response = getattr(error, "response", None)
    headers: Any = getattr(response, "headers", None)
    value = headers.get("Retry-After") if hasattr(headers, "get") else None
    if value is None:
        return _DEFAULT_RETRY_DELAY_SECONDS
    try:
        delay = float(value)
    except (TypeError, ValueError):
        return _DEFAULT_RETRY_DELAY_SECONDS
    if not math.isfinite(delay) or delay < 0:
        return _DEFAULT_RETRY_DELAY_SECONDS
    return min(delay, _MAX_RETRY_DELAY_SECONDS)


class RetryingLiteLlm(LiteLlm):
    """Retry exactly one explicit 429 before any model output is emitted.

    Google ADK mutates ``LlmRequest`` before it reaches LiteLLM.  The retry
    therefore uses a snapshot captured before attempt one; replaying the same
    instance would duplicate user content.  Once any response has been yielded,
    replay is unsafe because it could duplicate text, reasoning, or tool calls.
    """

    def __init__(self, *, model: str, **kwargs: Any) -> None:
        super().__init__(model=model, **kwargs)

    @override
    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse, None]:
        retry_request = copy.deepcopy(llm_request)
        emitted = False
        try:
            async for response in super().generate_content_async(
                llm_request,
                stream=stream,
            ):
                emitted = True
                yield response
            return
        except Exception as error:
            if emitted or _status_code(error) != 429:
                raise
            delay = _retry_delay_seconds(error)
            logger.info(
                "Retrying one pre-output LiteLLM request after HTTP 429 "
                "delay_seconds=%s",
                delay,
            )
            await asyncio.sleep(delay)

        async for response in super().generate_content_async(
            retry_request,
            stream=stream,
        ):
            yield response


__all__ = ["RetryingLiteLlm"]
