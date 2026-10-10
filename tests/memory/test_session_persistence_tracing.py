import asyncio

import pytest
from google.adk.events import Event
from google.adk.events.event_actions import EventActions
from google.adk.sessions import DatabaseSessionService
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from veadk.memory.short_term_memory_backends.sqlite_backend import SQLiteSTMBackend


@pytest.fixture
def tracing(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test.session")
    monkeypatch.setattr(trace, "get_tracer", lambda *args, **kwargs: tracer)
    yield tracer, exporter
    provider.shutdown()


@pytest.mark.asyncio
async def test_real_sqlite_persists_event_state_and_parent(tracing, tmp_path):
    tracer, exporter = tracing
    service = SQLiteSTMBackend(local_path=str(tmp_path / "session.db")).session_service
    session = await service.create_session(app_name="app", user_id="user")
    event = Event(
        author="agent", actions=EventActions(state_delta={"answer": "private"})
    )
    with tracer.start_as_current_span("execution") as parent:
        result = await service.append_event(session, event)
    reloaded = await service.get_session(
        app_name="app", user_id="user", session_id=session.id
    )
    assert result.id == event.id
    assert reloaded.state["answer"] == "private"
    assert reloaded.events[-1].id == event.id
    spans = [
        s
        for s in exporter.get_finished_spans()
        if s.name == "veadk.session.append_event"
    ]
    assert len(spans) == 1
    assert spans[0].parent.span_id == parent.get_span_context().span_id
    assert spans[0].end_time >= spans[0].start_time
    assert "private" not in spans[0].to_json()
    await service.db_engine.dispose()


@pytest.mark.asyncio
async def test_partial_event_is_not_persistence(tracing, tmp_path):
    _, exporter = tracing
    service = SQLiteSTMBackend(local_path=str(tmp_path / "partial.db")).session_service
    session = await service.create_session(app_name="app", user_id="user")
    await service.append_event(session, Event(author="agent", partial=True))
    assert not exporter.get_finished_spans()
    await service.db_engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [ValueError("private database credentials"), asyncio.CancelledError()]
)
async def test_failure_and_cancel_preserve_original_error(
    tracing, tmp_path, monkeypatch, error
):
    _, exporter = tracing
    service = SQLiteSTMBackend(local_path=str(tmp_path / "error.db")).session_service
    session = await service.create_session(app_name="app", user_id="user")

    async def fail(self, session, event):
        raise error

    monkeypatch.setattr(DatabaseSessionService, "append_event", fail)
    with pytest.raises(type(error)) as caught:
        await service.append_event(session, Event(author="agent"))
    assert caught.value is error
    span = exporter.get_finished_spans()[0]
    assert span.attributes["error.type"] == type(error).__name__
    assert "private database credentials" not in span.to_json()
    assert span.status.status_code == trace.StatusCode.ERROR
    await service.db_engine.dispose()


@pytest.mark.asyncio
async def test_telemetry_failure_does_not_skip_or_repeat_persistence(
    tmp_path, monkeypatch
):
    service = SQLiteSTMBackend(
        local_path=str(tmp_path / "fail-open.db")
    ).session_service
    session = await service.create_session(app_name="app", user_id="user")

    def fail(*args, **kwargs):
        raise RuntimeError("telemetry unavailable")

    monkeypatch.setattr(trace, "get_tracer", fail)
    event = Event(author="agent")
    await service.append_event(session, event)
    stored = await service.get_session(
        app_name="app", user_id="user", session_id=session.id
    )
    assert [e.id for e in stored.events].count(event.id) == 1
    await service.db_engine.dispose()


@pytest.mark.asyncio
async def test_real_runner_persists_events_within_execution(tracing, tmp_path):
    from google.adk.agents import BaseAgent
    from google.adk.runners import Runner
    from google.genai import types

    class ProbeAgent(BaseAgent):
        async def _run_async_impl(self, ctx):
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                content=types.Content(role="model", parts=[types.Part(text="probe")]),
                actions=EventActions(state_delta={"saved": True}),
            )

    tracer, exporter = tracing
    service = SQLiteSTMBackend(local_path=str(tmp_path / "runner.db")).session_service
    session = await service.create_session(app_name="app", user_id="user")
    runner = Runner(
        agent=ProbeAgent(name="probe"), app_name="app", session_service=service
    )
    with tracer.start_as_current_span("runtime.execution") as parent:
        events = [
            event
            async for event in runner.run_async(
                user_id="user",
                session_id=session.id,
                new_message=types.Content(role="user", parts=[types.Part(text="test")]),
            )
        ]
    reloaded = await service.get_session(
        app_name="app", user_id="user", session_id=session.id
    )
    assert reloaded.state["saved"] is True
    assert events[-1].id in [event.id for event in reloaded.events]
    saves = [
        s
        for s in exporter.get_finished_spans()
        if s.name == "veadk.session.append_event"
    ]
    assert len(saves) >= 2
    assert all(s.context.trace_id == parent.get_span_context().trace_id for s in saves)
    assert all(s.attributes["gen_ai.session.id"] == session.id for s in saves)
    assert any(
        s.attributes.get("gen_ai.invocation.id") == events[-1].invocation_id
        for s in saves
    )
    await service.db_engine.dispose()
