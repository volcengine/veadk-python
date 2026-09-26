"""Regression: projection metadata must follow persisted, nonpartial events."""

import asyncio
from contextlib import aclosing

import pytest
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
        # The first summary is triggered after eleven background turns in this
        # fixed, independently bounded fixture. Cancel its visible answer.
        for turn in range(10):
            client = Client("chatter")
            await collect(
                runner(service, client, fetch),
                f"Progress note {turn}: "
                + "Temporary background; preserve archived source. " * 22,
            )
            assert not client.summary_requests
        before = await service.get_session(**IDENTITY)
        client = Client("hold")
        task = asyncio.create_task(
            collect(
                runner(service, client, fetch),
                "Progress note 10: "
                + "Temporary background; preserve archived source. " * 22,
            )
        )
        async with asyncio.timeout(4):
            while not client.streams:
                await asyncio.sleep(0)
            await client.streams[-1].blocked.wait()
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
