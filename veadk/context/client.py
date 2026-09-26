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

"""Final admission at the public ADK LiteLLM client boundary."""

from __future__ import annotations

import asyncio
import copy

from google.adk.models.lite_llm import LiteLLMClient

from .attempts import AttemptLedger, current_attempts, is_context_overflow
from .budget import (
    ContextBudgetError,
    check_payload,
    fallback_config,
    model_limits,
    resolve_payload_budget,
)
from .config import ContextCompressionConfig
from .runtime import current_scope, is_summary
from .source_verification import source_verification_choice
from .tool_lookup_preview import apply_tool_lookup_previews
from .verification_preview import apply_lookup_previews


class BudgetedLiteLLMClient(LiteLLMClient):
    """Check each endpoint before delegating; never send SDK policy fields.

    Fallback selection lives here so a smaller fallback cannot bypass the
    budget. Stream consumption stays with ADK; errors after stream acquisition
    are never replayed by this client.
    """

    def __init__(self, delegate: LiteLLMClient, config: ContextCompressionConfig):
        self.delegate = delegate
        self.config = config

    async def acompletion(self, model, messages, tools=None, **kwargs):
        primary = dict(kwargs, model=model, messages=messages, tools=tools)
        fallbacks = primary.pop("fallbacks", None) or []
        if is_summary.get():
            fallbacks = []
            # The summarizer has no tools and no automatic retry/fallback path.
            for key in ("tools", "functions", "tool_choice", "function_call"):
                primary.pop(key, None)
            primary["tools"] = None
            primary["num_retries"] = 0
            if model_limits(model).get("ark_thinking_controls"):
                # Ark documents Chat thinking.type=disabled for this exact model.
                # Only the bounded extraction request changes; preserve Agent
                # reasoning settings and never mutate shared provider arguments.
                primary["extra_body"] = copy.deepcopy(primary.get("extra_body") or {})
                primary["extra_body"]["thinking"] = {"type": "disabled"}
                primary.pop("thinking", None)
                primary.pop("reasoning_effort", None)
        attempts: list[tuple[dict, ContextCompressionConfig | dict | None]] = [
            (primary, self.config)
        ]
        for endpoint in fallbacks:
            values: dict = (
                {"model": endpoint}
                if isinstance(endpoint, str)
                else copy.deepcopy(endpoint)
            )
            override = values.pop("context_compression", None)
            attempts.append(({**primary, **values}, override))
        failure = None
        ledger = current_attempts.get() or AttemptLedger(
            1 if is_summary.get() else self.config.max_model_attempts,
            self.config.request_timeout_seconds,
            summary_timeout=self.config.summary_time_budget_seconds,
        )
        protected = resolve_payload_budget(primary, self.config) is not None
        for index, (attempt, override) in enumerate(attempts):
            try:
                policy = (
                    fallback_config(
                        str(attempt.get("model", "")),
                        self.config,
                        override,
                        payload=attempt,
                    )
                    if index and protected
                    else self.config
                )
                choice = source_verification_choice(attempt, policy)
                if choice:
                    attempt = {**attempt, "tool_choice": choice}
                    attempt = apply_lookup_previews(attempt)
                    attempt = apply_tool_lookup_previews(attempt)
                check_payload(attempt, policy)
                remaining = ledger.claim()
                # Provider retries cannot multiply our bounded SDK attempts.
                attempt["num_retries"] = 0
                if choice:
                    scope = current_scope.get()
                    if scope:
                        # At most one transport attempt per invocation. A
                        # failure or invalid reader call must not force a loop.
                        scope.source_verification_attempted = True
                response = await asyncio.wait_for(
                    self.delegate.acompletion(**attempt), timeout=remaining
                )
                if attempt.get("stream"):
                    ledger.streams.append(response)
                return response
            except Exception as error:
                failure = error
                if is_context_overflow(error):
                    raise
                # Configuration errors cannot be repaired by trying providers.
                if (
                    isinstance(error, ContextBudgetError)
                    and error.code != "input_too_large"
                ):
                    raise
        assert failure is not None
        raise failure

    def completion(self, model, messages, tools=None, stream=False, **kwargs):
        check_payload(
            dict(kwargs, model=model, messages=messages, tools=tools, stream=stream),
            self.config,
        )
        if kwargs.get("fallbacks"):
            raise ContextBudgetError("synchronous_fallback_unsupported")
        kwargs["num_retries"] = 0
        return self.delegate.completion(model, messages, tools, stream=stream, **kwargs)
