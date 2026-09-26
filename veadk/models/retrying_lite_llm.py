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
from contextlib import aclosing
from typing import Any

from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from typing_extensions import override

from veadk.context.attempts import (
    AttemptLedger,
    current_attempts,
    is_context_overflow,
    next_with_deadline,
)
from veadk.context.budget import (
    ContextBudgetError,
    check_payload,
    request_payload,
)
from veadk.context.client import BudgetedLiteLLMClient
from veadk.context.config import resolve_config
from veadk.context.manager import prepare_context, recover_context
from veadk.context.runtime import is_summary
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


def _copy_retry_request(llm_request: LlmRequest) -> LlmRequest:
    retry_request = LlmRequest(
        model=llm_request.model,
        contents=copy.deepcopy(llm_request.contents),
        config=copy.deepcopy(llm_request.config),
        live_connect_config=copy.deepcopy(llm_request.live_connect_config),
        cache_config=copy.deepcopy(llm_request.cache_config),
        cache_metadata=copy.deepcopy(llm_request.cache_metadata),
        cacheable_contents_token_count=llm_request.cacheable_contents_token_count,
        previous_interaction_id=llm_request.previous_interaction_id,
    )
    retry_request.tools_dict = dict(llm_request.tools_dict)
    return retry_request


class RetryingLiteLlm(LiteLlm):
    """Retry exactly one explicit 429 before any model output is emitted.

    Google ADK mutates ``LlmRequest`` before it reaches LiteLLM.  The retry
    therefore uses a snapshot captured before attempt one; replaying the same
    instance would duplicate user content.  Once any response has been yielded,
    replay is unsafe because it could duplicate text, reasoning, or tool calls.
    """

    def __init__(self, *, model: str, **kwargs: Any) -> None:
        context_config = resolve_config(kwargs.pop("context_compression", None))
        super().__init__(model=model, **kwargs)
        self._context_config = context_config
        self.llm_client = BudgetedLiteLLMClient(self.llm_client, context_config)
        self._fallbacks_template = copy.deepcopy(
            getattr(self, "_additional_args", {}).get("fallbacks")
        )

    def _refresh_fallbacks(self) -> None:
        """Give LiteLLM a fresh fallback list for each call.

        LiteLLM's lightweight fallback helper mutates dict fallback entries when
        selecting their model. Keep VeADK's model object reusable across turns.
        """
        if self._fallbacks_template is not None:
            self._additional_args["fallbacks"] = copy.deepcopy(self._fallbacks_template)

    def with_context_compression(self, config):
        """Copy policy without mutating a model shared by multiple Agents."""
        clone = self.model_copy()
        clone._additional_args = copy.deepcopy(self._additional_args)
        clone._context_config = resolve_config(
            {
                **self._context_config.model_dump(),
                **resolve_config(config).model_dump(exclude_unset=True),
            }
        )
        delegate = self.llm_client
        if isinstance(delegate, BudgetedLiteLLMClient):
            delegate = delegate.delegate
        clone.llm_client = BudgetedLiteLLMClient(delegate, clone._context_config)
        return clone

    @property
    def context_compression_status(self):
        from veadk.context.status import describe_context

        return describe_context(self, self._context_config)

    @override
    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse, None]:
        ledger = AttemptLedger(
            1 if is_summary.get() else self._context_config.max_model_attempts,
            self._context_config.request_timeout_seconds,
            summary_timeout=self._context_config.summary_time_budget_seconds,
        )
        token = current_attempts.set(ledger)
        try:
            async with aclosing(
                self._generate_managed(llm_request, stream)
            ) as responses:
                while True:
                    try:
                        response = await next_with_deadline(responses, ledger)
                    except StopAsyncIteration:
                        break
                    yield response
        finally:
            try:
                await ledger.close_streams()
            finally:
                current_attempts.reset(token)

    async def _generate_managed(self, llm_request: LlmRequest, stream: bool):
        dispatch_tools = llm_request.tools_dict
        original_request = _copy_retry_request(llm_request)
        llm_request = _copy_retry_request(llm_request)
        await prepare_context(
            llm_request, self, self._context_config, self._additional_args
        )
        from veadk.context.tool_results import READ_CONTEXT_TOOL

        if READ_CONTEXT_TOOL in llm_request.tools_dict:
            dispatch_tools[READ_CONTEXT_TOOL] = llm_request.tools_dict[
                READ_CONTEXT_TOOL
            ]
        check_payload(
            {
                **self._additional_args,
                **request_payload(llm_request),
                "model": llm_request.model or self.model,
            },
            self._context_config,
        )
        quota_retried = False
        context_recovered = False
        while True:
            emitted = False
            try:
                self._refresh_fallbacks()
                async with aclosing(
                    super().generate_content_async(
                        _copy_retry_request(llm_request),
                        stream=stream,
                    )
                ) as responses:
                    async for response in responses:
                        emitted = True
                        yield response
                return
            except Exception as error:
                if emitted or is_summary.get():
                    raise
                if (
                    isinstance(error, ContextBudgetError)
                    and error.code == "input_too_large"
                    and not context_recovered
                    and self._context_config.mode != "off"
                ):
                    # Client admission failed before any network attempt. Plan
                    # once more with the measured final-payload overhead.
                    from veadk.context.budget import count_input

                    context_recovered = True
                    overhead = max(
                        256,
                        error.input_tokens
                        - count_input(
                            request_payload(llm_request), self._context_config
                        )
                        + 256,
                    )
                    llm_request = await recover_context(
                        original_request,
                        llm_request,
                        self,
                        self._context_config,
                        self._additional_args,
                        input_overhead=overhead,
                    )
                    if READ_CONTEXT_TOOL in llm_request.tools_dict:
                        dispatch_tools[READ_CONTEXT_TOOL] = llm_request.tools_dict[
                            READ_CONTEXT_TOOL
                        ]
                    continue
                if is_context_overflow(error):
                    if context_recovered or self._context_config.mode == "off":
                        raise ContextBudgetError("provider_context_limit") from None
                    context_recovered = True
                    recovered = await recover_context(
                        original_request,
                        llm_request,
                        self,
                        self._context_config,
                        self._additional_args,
                    )
                    llm_request = recovered
                    if READ_CONTEXT_TOOL in recovered.tools_dict:
                        dispatch_tools[READ_CONTEXT_TOOL] = recovered.tools_dict[
                            READ_CONTEXT_TOOL
                        ]
                    continue
                if quota_retried or _status_code(error) != 429:
                    raise
                quota_retried = True
                delay = _retry_delay_seconds(error)
                ledger = current_attempts.get()
                remaining = ledger.remaining() if ledger is not None else None
                if remaining is not None and delay >= remaining:
                    raise ContextBudgetError("request_time_budget_exhausted") from None
                logger.info(
                    "Retrying one pre-output LiteLLM HTTP 429; delay_seconds=%s", delay
                )
                await asyncio.sleep(delay)


__all__ = ["RetryingLiteLlm"]
