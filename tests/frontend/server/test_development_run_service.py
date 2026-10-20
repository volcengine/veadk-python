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

import pytest

from frontend.server.intelligent_development_runs.repository import RunRepository
from frontend.server.intelligent_development_runs.service import RunService


@pytest.mark.asyncio
async def test_browser_detach_preserves_worker_and_replays_output(tmp_path):
    repository = RunRepository(tmp_path / "runs.db")
    started, complete = asyncio.Event(), asyncio.Event()

    async def execute(run, token):
        await repository.append_event(
            run.owner_id, run.id, token, "delta", {"text": "kept"}
        )
        started.set()
        await complete.wait()
        await repository.finish(run.owner_id, run.id, token, 1)

    run = await repository.create("alice", "environment", "initial", "build")
    service = RunService(repository, execute)
    try:
        service.launch(run)
        await asyncio.wait_for(started.wait(), 2)
        subscription = service.subscribe("alice", run.id)
        await anext(subscription)
        await subscription.aclose()
        assert not (await repository.get("alice", run.id)).stop_requested
        complete.set()

        async def collect_replay():
            return [event async for event in service.subscribe("alice", run.id)]

        replay = await asyncio.wait_for(collect_replay(), 2)
        assert any(event and event["payload"].get("text") == "kept" for event in replay)
        assert (await repository.get("alice", run.id)).state == "succeeded"
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_shutdown_detaches_and_restart_claims_same_run(tmp_path):
    repository = RunRepository(tmp_path / "runs.db")
    started, detached, recovered = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def execute(run, token):
        await repository.update(
            run.owner_id,
            run.id,
            token,
            state="running",
            thread_id="thread-a",
            turn_id="turn-a",
        )
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            detached.set()

    run = await repository.create("alice", "environment", "initial", "build")
    service = RunService(repository, execute)
    service.launch(run)
    await asyncio.wait_for(started.wait(), 2)
    await service.close()
    assert detached.is_set()
    stored = await repository.get("alice", run.id)
    assert (
        not stored.stop_requested
        and stored.thread_id == "thread-a"
        and stored.turn_id == "turn-a"
    )

    async def recover(current, token):
        assert current.id == run.id
        assert current.thread_id == "thread-a" and current.turn_id == "turn-a"
        await repository.finish(current.owner_id, current.id, token, 1)
        recovered.set()

    restarted = RunService(RunRepository(repository.path), recover)
    try:
        await restarted.start()
        await asyncio.wait_for(recovered.wait(), 2)
    finally:
        await restarted.close()
