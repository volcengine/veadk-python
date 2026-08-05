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

import pytest

from frontend.server.evaluation_automation.models import RunSseActivity
from frontend.server.evaluation_automation.scheduler import QuietSessionScheduler


def _activity(session_id: str = "session-1") -> RunSseActivity:
    return RunSseActivity.from_proxy(
        {
            "app_name": "agent",
            "user_id": "user",
            "session_id": session_id,
        },
        runtime_id="runtime",
        region="cn-beijing",
        project_name="default",
        runtime_endpoint="https://runtime.example",
        runtime_authorization="Bearer secret",
    )


@pytest.mark.asyncio
async def test_new_activity_replaces_the_previous_quiet_task() -> None:
    gate = asyncio.Event()
    completed: list[RunSseActivity] = []

    async def sleep(_: float) -> None:
        await gate.wait()

    async def worker(activity: RunSseActivity) -> None:
        completed.append(activity)

    scheduler = QuietSessionScheduler(300, worker, sleep=sleep)
    first = _activity()
    second = first.model_copy(update={"project_name": "new-project"})

    scheduler.schedule(first)
    scheduler.schedule(second)
    gate.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert completed == [second]
    assert scheduler.pending_count == 0
    await scheduler.close()


@pytest.mark.asyncio
async def test_session_start_invalidates_a_pending_evaluation() -> None:
    completed: list[RunSseActivity] = []

    async def worker(activity: RunSseActivity) -> None:
        completed.append(activity)

    scheduler = QuietSessionScheduler(0, worker)
    activity = _activity()
    scheduler.schedule(activity)
    scheduler.invalidate(activity.key)
    await asyncio.sleep(0)

    assert completed == []
    await scheduler.close()
