from __future__ import annotations

from frontend.server.evaluation_automation.models import RunSseActivity
from frontend.server.evaluation_automation.sse import (
    RunSseObservation,
    observed_sse_stream,
)


def _activity() -> RunSseActivity:
    return RunSseActivity.from_proxy(
        {"app_name": "agent", "user_id": "user", "session_id": "session"},
        runtime_id="runtime",
        region="cn-beijing",
        project_name="default",
        runtime_endpoint="https://runtime.example",
        runtime_authorization="Bearer secret",
    )


def test_sse_observation_accepts_a_completed_event_stream() -> None:
    observation = RunSseObservation(_activity())
    observation.feed(b'data: {"id":"event-1","author":"agent"}\n\n')
    observation.finish()

    assert observation.succeeded


def test_sse_observation_rejects_an_error_split_across_chunks() -> None:
    observation = RunSseObservation(_activity())
    observation.feed(b'data: {"err')
    observation.feed(b'or":"model failed"}\n\n')
    observation.finish()

    assert not observation.succeeded


def test_sse_observation_requires_at_least_one_json_event() -> None:
    observation = RunSseObservation(_activity())
    observation.feed(b": keep-alive\n\ndata: [DONE]\n\n")
    observation.finish()

    assert not observation.succeeded


def test_sse_observation_flushes_an_unterminated_final_event() -> None:
    observation = RunSseObservation(_activity())
    observation.feed(b'data: {"id":"event-1","author":"agent"}')

    assert not observation.succeeded
    observation.finish()
    assert observation.succeeded


def test_sse_observation_recognizes_compatible_error_fields() -> None:
    observation = RunSseObservation(_activity())
    observation.feed(b'data: {"errorMessage":"model failed"}\n\n')
    observation.finish()

    assert not observation.succeeded


async def _chunks(*values: bytes):
    for value in values:
        yield value


async def _consume(stream) -> list[bytes]:
    return [chunk async for chunk in stream]


def test_observed_stream_notifies_after_normal_eof() -> None:
    completed: list[RunSseActivity] = []
    observation = RunSseObservation(_activity())

    import asyncio

    chunks = asyncio.run(
        _consume(
            observed_sse_stream(
                _chunks(b'data: {"id":"event-1"}\n\n'),
                observation,
                completed.append,
            )
        )
    )

    assert chunks == [b'data: {"id":"event-1"}\n\n']
    assert completed == [observation.activity]


def test_observed_stream_does_not_notify_after_consumer_disconnect() -> None:
    completed: list[RunSseActivity] = []
    observation = RunSseObservation(_activity())

    async def consume_one_and_disconnect() -> None:
        stream = observed_sse_stream(
            _chunks(
                b'data: {"id":"event-1"}\n\n',
                b'data: {"id":"event-2"}\n\n',
            ),
            observation,
            completed.append,
        )
        await anext(stream)
        await stream.aclose()

    import asyncio

    asyncio.run(consume_one_and_disconnect())

    assert completed == []
