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

"""Regression: projection metadata must follow persisted, nonpartial events."""

import asyncio
from contextlib import aclosing

import pytest

from veadk.context.attempts import timeout
from test_streaming_session import IDENTITY, RUN, Client, message, runner, setup

from veadk.context.runtime import current_scope
from veadk.memory.short_term_memory import ShortTermMemory


async def collect(agent_runner, text):
    # Newer ADK versions reuse EventActions across partial and final events.
    # Assert the metadata visible at emission time, before later mutations.
    async with aclosing(
        agent_runner.run_async(
            user_id=IDENTITY["user_id"],
            session_id=IDENTITY["session_id"],
            new_message=message(text),
            run_config=RUN,
        )
    ) as events:
        return [event.model_copy(deep=True) async for event in events]


def projections(state):
    return {k: v for k, v in state.items() if k.startswith("veadk:context:")}


@pytest.mark.asyncio
async def test_stream_summary_cache_is_committed_then_reused_after_restart(tmp_path):
    service, fetch, _source, count, original = await setup(tmp_path)
    try:
        for turn in range(36):
            client = Client("chatter")
            events = await collect(
                runner(service, client, fetch),
                f"Progress note {turn}: "
                + "Temporary background; preserve archived source. " * 22,
            )
            if not client.summary_requests:
                continue
            # ADK may repeat already committed actions in later usage chunks.
            # The first event introducing the cache must be persistable.
            introduced = [e for e in events if projections(e.actions.state_delta)]
            assert introduced and not introduced[0].partial
            committed = [
                e
                for e in events
                if not e.partial and projections(e.actions.state_delta)
            ]
            assert committed, "summary metadata must be attached to a persisted event"
            saved = await service.get_session(**IDENTITY)
            cache = projections(saved.state)
            assert cache and cache == projections(committed[-1].actions.state_delta)
            prior = [e.model_dump(mode="json") for e in saved.events]
            await service.close()
            service = ShortTermMemory(
                backend="sqlite", local_database_path=str(tmp_path / "session.sqlite3")
            ).session_service
            restored = await service.get_session(**IDENTITY)
            assert [e.model_dump(mode="json") for e in restored.events] == prior
            assert projections(restored.state) == cache
            next_client = Client("chatter")
            await collect(
                runner(service, next_client, fetch),
                "Continue the same task. Reply briefly.",
            )
            assert next_client.summary_requests == [], (
                "a fitting committed prefix must be reused"
            )
            assert count[0] == 1
            assert [
                e.model_dump(mode="json") for e in restored.events[: len(original)]
            ] == original
            break
        else:
            pytest.fail("fixture did not trigger an actual summary")
    finally:
        await service.close()
    assert current_scope.get() is None


@pytest.mark.asyncio
async def test_cancelling_summary_stream_does_not_commit_partial_projection(tmp_path):
    service, fetch, _source, count, _original = await setup(tmp_path)
    try:

        class HoldFirstSummary(Client):
            async def acompletion(self, **kwargs):
                # Hold the answer following an actual summary, regardless of
                # how many turns the active projection budget can retain.
                if self.summary_requests:
                    self.mode = "hold"
                return await super().acompletion(**kwargs)

        task = None
        for turn in range(36):
            before = await service.get_session(**IDENTITY)
            client = HoldFirstSummary("chatter")
            task = asyncio.create_task(
                collect(
                    runner(service, client, fetch),
                    f"Progress note {turn}: "
                    + "Temporary background; preserve archived source. " * 22,
                )
            )
            try:
                async with timeout(4):
                    while not task.done() and not (
                        client.streams and client.streams[-1].blocked.is_set()
                    ):
                        await asyncio.sleep(0)
            except BaseException:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise
            if client.summary_requests:
                assert client.streams[-1].blocked.is_set() and not task.done()
                break
            await task
        else:
            pytest.fail("fixture did not trigger an actual summary")
        assert client.summary_requests
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        after = await service.get_session(**IDENTITY)
        assert projections(after.state) == projections(before.state)
        assert not any(e.partial for e in after.events)
        retry = Client("chatter")
        await collect(
            runner(service, retry, fetch), "Continue the same task after interruption."
        )
        assert retry.summary_requests
        assert projections((await service.get_session(**IDENTITY)).state)
        assert count[0] == 1
    finally:
        await service.close()
