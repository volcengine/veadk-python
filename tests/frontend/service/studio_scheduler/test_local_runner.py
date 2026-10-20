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

import asyncio
from datetime import datetime, timezone

import pytest

from frontend.service.studio_scheduler.local_runner import run_local_scheduler
from frontend.service.studio_scheduler.models import DispatchSummary


@pytest.mark.asyncio
async def test_local_scheduler_dispatches_current_minute_then_waits_for_boundary() -> (
    None
):
    now = datetime(2026, 8, 20, 10, 35, 42, tzinfo=timezone.utc)
    dispatched: list[datetime] = []
    delays: list[float] = []

    class _Dispatcher:
        async def dispatch_minute(self, now: datetime) -> DispatchSummary:
            dispatched.append(now)
            return DispatchSummary()

        async def execute_ready(self, now: datetime | None = None) -> DispatchSummary:
            return DispatchSummary()

    async def stop_after_wait(delay: float) -> None:
        delays.append(delay)
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await run_local_scheduler(
            _Dispatcher(),
            clock=lambda: now,
            sleep=stop_after_wait,
        )

    assert dispatched == [now.replace(second=0)]
    assert sorted(delays) == [1.0, 18.0]
