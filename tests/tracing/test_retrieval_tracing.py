import asyncio

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from veadk.tracing.retrieval_tracing import retrieval_span


@pytest.fixture
def telemetry(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "get_tracer", provider.get_tracer)
    yield provider, exporter
    provider.shutdown()


@pytest.mark.parametrize("outcome", ["success", "failure", "cancel"])
def test_parent_cleanup_and_redaction(telemetry, outcome):
    provider, exporter = telemetry
    with provider.get_tracer("test").start_as_current_span("parent") as parent:
        try:
            with retrieval_span(
                "veadk.memory.search", backend="openviking"
            ) as operation:
                operation.set_attribute("veadk.retrieval.result_count", 0)
                if outcome == "failure":
                    raise ValueError("sensitive query and token")
                if outcome == "cancel":
                    raise asyncio.CancelledError("sensitive query and token")
        except (ValueError, asyncio.CancelledError):
            pass
        assert trace.get_current_span() is parent
    span = exporter.get_finished_spans()[0]
    assert span.parent.span_id == parent.get_span_context().span_id
    assert span.attributes["veadk.retrieval.backend"] == "openviking"
    assert not span.events
    assert "sensitive" not in str(span.attributes)
    assert (span.status.status_code == StatusCode.ERROR) == (outcome != "success")


def test_telemetry_failure_does_not_repeat_business(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("telemetry unavailable")

    monkeypatch.setattr(trace, "get_tracer", fail)
    calls = []
    with retrieval_span("veadk.memory.save", backend="local") as operation:
        calls.append("save")
        operation.set_attribute("veadk.memory.event_count", 1)
    assert calls == ["save"]


@pytest.mark.parametrize("error", [False, True])
def test_knowledge_boundary(telemetry, error, monkeypatch):
    from types import SimpleNamespace
    from veadk.knowledgebase.knowledgebase import KnowledgeBase

    def search(**kwargs):
        assert kwargs == {"query": "private-query", "top_k": 3}
        if error:
            raise ValueError("private-query")
        return ["private-result"]

    monkeypatch.setattr(
        KnowledgeBase,
        "model_post_init",
        lambda instance, *args: object.__setattr__(
            instance, "_backend", SimpleNamespace(search=search)
        ),
    )
    kb = KnowledgeBase.model_construct(backend="local", top_k=3)
    kb._backend = SimpleNamespace(search=search)
    if error:
        with pytest.raises(ValueError):
            kb.search("private-query")
    else:
        assert kb.search("private-query")[0].content == "private-result"
    spans = telemetry[1].get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "veadk.knowledge.search"
    assert spans[0].attributes["veadk.retrieval.top_k"] == 3
    assert "private" not in str(spans[0].attributes)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [False, True])
async def test_memory_empty_result_distinguishes_failure(telemetry, error, monkeypatch):
    from types import SimpleNamespace
    from veadk.memory.long_term_memory import LongTermMemory

    def search(**kwargs):
        if error:
            raise ValueError("private-query")
        return []

    monkeypatch.setattr(LongTermMemory, "model_post_init", lambda *args: None)
    memory = LongTermMemory.model_construct(backend="local", top_k=3)
    memory._backend = SimpleNamespace(search_memory=search)
    response = await memory.search_memory(
        app_name="test", user_id="private-user", query="private-query"
    )
    assert response.memories == []
    spans = telemetry[1].get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "veadk.memory.search"
    assert (spans[0].status.status_code == StatusCode.ERROR) == error
    assert "private" not in str(spans[0].attributes)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [False, True])
async def test_memory_save_boundary(telemetry, error, monkeypatch):
    from types import SimpleNamespace
    from google.adk.sessions import Session
    from veadk.memory.long_term_memory import LongTermMemory

    calls = []

    def save(**kwargs):
        calls.append(kwargs)
        if error:
            raise ValueError("private-memory")

    monkeypatch.setattr(LongTermMemory, "model_post_init", lambda *args: None)
    memory = LongTermMemory.model_construct(backend="local", top_k=3)
    memory._backend = SimpleNamespace(save_memory=save)
    session = Session(
        id="session-test", app_name="test", user_id="private-user", state={}, events=[]
    )
    if error:
        with pytest.raises(ValueError):
            await memory.add_session_to_memory(session)
    else:
        await memory.add_session_to_memory(session)
    assert len(calls) == 1
    assert calls[0]["user_id"] == "private-user"
    span = telemetry[1].get_finished_spans()[0]
    assert span.name == "veadk.memory.save"
    assert span.attributes["session.id"] == "session-test"
    assert span.attributes["veadk.memory.event_count"] == 0
    assert (span.status.status_code == StatusCode.ERROR) == error
    assert "private" not in str(span.attributes)


@pytest.mark.asyncio
async def test_threaded_search_keeps_concurrent_parent_context(telemetry, monkeypatch):
    import threading
    from types import SimpleNamespace
    from veadk.memory.long_term_memory import LongTermMemory

    barrier = threading.Barrier(2)
    parent_by_query = {}
    observed = {}
    monkeypatch.setattr(LongTermMemory, "model_post_init", lambda *args: None)
    memory = LongTermMemory.model_construct(backend="openviking", top_k=3)

    def search(**kwargs):
        observed[kwargs["query"]] = trace.get_current_span().get_span_context()
        barrier.wait(timeout=3)
        return []

    memory._backend = SimpleNamespace(search_memory=search)

    async def request(query):
        with telemetry[0].get_tracer("test").start_as_current_span(query) as parent:
            parent_by_query[query] = parent.get_span_context()
            await memory.search_memory(app_name="test", user_id="user", query=query)
            assert trace.get_current_span() is parent

    await asyncio.gather(request("first"), request("second"))
    spans = {span.context.span_id: span for span in telemetry[1].get_finished_spans()}
    for query, child in observed.items():
        assert spans[child.span_id].parent.span_id == parent_by_query[query].span_id
        assert child.trace_id == parent_by_query[query].trace_id


@pytest.mark.asyncio
@pytest.mark.parametrize("operation_name", ["search", "save"])
async def test_thread_cancellation_finishes_caller_without_claiming_backend_end(
    telemetry, monkeypatch, operation_name
):
    import threading
    from types import SimpleNamespace
    from veadk.memory.long_term_memory import LongTermMemory

    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    monkeypatch.setattr(LongTermMemory, "model_post_init", lambda *args: None)
    memory = LongTermMemory.model_construct(backend="openviking", top_k=3)

    def search(**kwargs):
        started.set()
        try:
            assert release.wait(timeout=3)
            return []
        finally:
            finished.set()

    memory._backend = SimpleNamespace(search_memory=search, save_memory=search)
    if operation_name == "search":
        call = memory.search_memory(app_name="test", user_id="user", query="query")
    else:
        from google.adk.sessions import Session

        call = memory.add_session_to_memory(
            Session(
                id="cancel-session",
                app_name="test",
                user_id="user",
                state={},
                events=[],
            )
        )
    task = asyncio.create_task(call)
    try:
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not finished.is_set()
        span = telemetry[1].get_finished_spans()[0]
        assert span.attributes["error.type"] == "CancelledError"
        assert span.status.status_code == StatusCode.ERROR
        assert "veadk.retrieval.result_count" not in span.attributes
    finally:
        release.set()
        assert await asyncio.to_thread(finished.wait, 2)


def test_span_mutation_and_end_failure_preserve_business_error(monkeypatch):
    class BrokenSpan:
        def set_attribute(self, *args):
            raise RuntimeError("telemetry attribute failed")

        def set_status(self, *args):
            raise RuntimeError("telemetry status failed")

        def end(self):
            raise RuntimeError("telemetry end failed")

        def get_span_context(self):
            return trace.INVALID_SPAN_CONTEXT

    from types import SimpleNamespace

    monkeypatch.setattr(
        trace,
        "get_tracer",
        lambda *args: SimpleNamespace(start_span=lambda *a: BrokenSpan()),
    )
    original = ValueError("business failure")
    with pytest.raises(ValueError) as raised:
        with retrieval_span("veadk.knowledge.search", backend="local") as operation:
            operation.set_attribute("veadk.retrieval.top_k", 3)
            raise original
    assert raised.value is original


@pytest.mark.asyncio
async def test_real_knowledge_tool_thread_inherits_tool_parent(telemetry, monkeypatch):
    from types import SimpleNamespace
    from veadk.knowledgebase.knowledgebase import KnowledgeBase
    from veadk.tools.builtin_tools.load_knowledgebase import LoadKnowledgebaseTool

    monkeypatch.setattr(
        KnowledgeBase,
        "model_post_init",
        lambda instance, *args: object.__setattr__(
            instance, "_backend", SimpleNamespace(search=lambda **kwargs: ["result"])
        ),
    )
    kb = KnowledgeBase.model_construct(backend="local", top_k=3)
    tool = LoadKnowledgebaseTool(knowledgebase=kb)
    with telemetry[0].get_tracer("test").start_as_current_span("tool") as parent:
        response = await tool.load_knowledgebase("private-query", tool_context=None)
        assert trace.get_current_span() is parent
    assert response.knowledges[0].content == "result"
    child = telemetry[1].get_finished_spans()[0]
    assert child.name == "veadk.knowledge.search"
    assert child.parent.span_id == parent.get_span_context().span_id


def test_sensitive_attributes_are_not_recorded(telemetry):
    with retrieval_span("veadk.memory.search", backend="local") as operation:
        operation.set_attribute("query", "private-query")
        operation.set_attribute("user.id", "private-user")
        operation.set_attribute("endpoint", "private-endpoint")
    assert dict(telemetry[1].get_finished_spans()[0].attributes) == {
        "veadk.retrieval.backend": "local"
    }
