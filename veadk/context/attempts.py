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

"""One request ledger for retry, fallback and context recovery."""

from __future__ import annotations

import asyncio
import inspect
import sys
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

if sys.version_info >= (3, 11):
    from asyncio import timeout
else:  # Python 3.10; existing SDK dependency.
    from async_timeout import timeout

from .budget import ContextBudgetError


@dataclass
class AttemptLedger:
    maximum: int
    timeout: float | None
    used: int = 0
    started: float = field(default_factory=time.monotonic)
    streams: list[Any] = field(default_factory=list, repr=False)
    summary_timeout: float = 90

    def remaining(self) -> float | None:
        if self.timeout is None:
            return None
        remaining = self.timeout - (time.monotonic() - self.started)
        if remaining <= 0:
            raise ContextBudgetError("request_time_budget_exhausted")
        return remaining

    def claim(self) -> float | None:
        remaining = self.remaining()
        if self.used >= self.maximum:
            raise ContextBudgetError("model_attempt_budget_exhausted")
        self.used += 1
        return remaining

    def summary_remaining(self, ratio: float) -> float:
        """Bound summary work even without an additional main-request deadline.

        Chunks, merges and recovery share this deadline; starting another
        summary must never reset it. Preserve the parent timeout classification.
        """
        self.remaining()  # Preserve an exhausted explicit request's error code.
        budget = self.summary_timeout
        if self.timeout is not None:
            budget = min(budget, self.timeout * ratio)
        remaining = budget - (time.monotonic() - self.started)
        if remaining <= 0:
            raise ContextBudgetError("summary_time_budget_exhausted")
        return remaining

    async def close_streams(self):
        while self.streams:
            await close_stream(self.streams.pop())


async def close_stream(stream):
    close = getattr(stream, "aclose", None) or getattr(stream, "close", None)
    if callable(close):
        try:
            result = close()
            if inspect.isawaitable(result):
                await result
        except Exception:  # noqa: BLE001,S110 - cleanup must not mask failure or log payloads.
            pass


async def next_with_deadline(iterator, ledger):
    # Consume in the same task: ADK tracing uses ContextVar tokens across yields.
    # The timer only runs while consuming, never while control is with the caller.
    remaining = ledger.remaining()
    if remaining is None:
        return await iterator.__anext__()
    try:
        async with timeout(remaining):
            return await iterator.__anext__()
    except (asyncio.TimeoutError, TimeoutError):
        # A transport can time out before our deadline. Keep that distinction.
        ledger.remaining()
        raise


current_attempts: ContextVar[AttemptLedger | None] = ContextVar(
    "veadk_context_attempts", default=None
)


def is_context_overflow(error: Exception) -> bool:
    """Recognize explicit types/codes; never parse arbitrary exception text."""
    from litellm.exceptions import ContextWindowExceededError

    if isinstance(error, ContextWindowExceededError):
        return True
    body = getattr(error, "body", None)
    if not isinstance(body, dict):
        return False
    error_data = body.get("error", body)
    return (
        isinstance(error_data, dict)
        and error_data.get("code") == "context_length_exceeded"
    )
