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

"""Minute-aligned scheduler loop used only by local Studio development."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Protocol

from .models import DispatchSummary

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]
Sleeper = Callable[[float], Awaitable[None]]


class MinuteDispatcher(Protocol):
    async def dispatch_minute(self, now: datetime) -> DispatchSummary: ...


async def run_local_scheduler(
    dispatcher: MinuteDispatcher,
    *,
    clock: Clock | None = None,
    sleep: Sleeper = asyncio.sleep,
) -> None:
    """Dispatch each observed UTC minute once until the task is cancelled."""
    get_now = clock or (lambda: datetime.now(timezone.utc))
    last_dispatched: datetime | None = None
    while True:
        now = get_now()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("local scheduler clock must include a timezone")
        minute = now.astimezone(timezone.utc).replace(second=0, microsecond=0)
        if minute != last_dispatched:
            last_dispatched = minute
            try:
                summary = await dispatcher.dispatch_minute(minute)
                logger.debug(
                    "Local Studio scheduler scanned=%s started=%s failed=%s",
                    summary.scanned,
                    summary.started,
                    summary.failed,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Local Studio scheduler failed for %s", minute)
        next_minute = minute + timedelta(minutes=1)
        delay = max(0.01, (next_minute - get_now()).total_seconds())
        await sleep(delay)


__all__ = ["run_local_scheduler"]
