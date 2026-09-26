"""Recoverable projections must retain exact sources, scope and hard budgets."""

import copy
import json
from types import SimpleNamespace

import pytest
from google.adk.events import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.sessions import Session
from google.adk.tools.function_tool import FunctionTool
from google.genai import types

from veadk.context.config import ContextCompressionConfig
from veadk.context.runtime import ContextScope, current_scope
from veadk.context.tool_results import READ_CONTEXT_TOOL, compact_tool_results


def mcp_source(text, **metadata):
    def fetch() -> dict:
        raise AssertionError("Original business tool must never run during retrieval")

    tool = FunctionTool(fetch)
    tool.custom_metadata = {"mcp_text_preview": True, **metadata}
    response = types.FunctionResponse(
        id="fetch-1",
        name="fetch",
        response={"content": [{"type": "text", "text": text}], "isError": False},
    )
    event = Event(
        id="source",
        author="agent",
        content=types.Content(
            role="user", parts=[types.Part(function_response=response)]
        ),
    )
    scope = ContextScope(
        session=Session(id="session", app_name="app", user_id="user", events=[event]),
        agent_name="agent",
        branch="",
    )
    request = LlmRequest(
        contents=[copy.deepcopy(event.content)], tools_dict={"fetch": tool}
    )
    return request, scope


async def read(request, scope, reference, **kwargs):
    token = current_scope.set(scope)
    try:
        return await request.tools_dict[READ_CONTEXT_TOOL].func(
            reference=reference,
            tool_context=SimpleNamespace(
                session=scope.session, agent_name=scope.agent_name
            ),
            **kwargs,
        )
    finally:
        current_scope.reset(token)


@pytest.mark.asyncio
async def test_native_mcp_preview_reads_exact_middle_without_changing_session():
    text = "a" * 20000 + "Exact evidence: 812.37 CNY" + "z" * 20000
    request, scope = mcp_source(text)
    original = scope.session.model_dump()
    refs = compact_tool_results(request, scope, ContextCompressionConfig())
    assert refs, "MCP content[].text must have a recoverable source"
    result = await read(request, scope, next(iter(refs)), query="Exact evidence")
    assert "812.37 CNY" in result["text"]
    assert scope.session.events[0].model_dump() == original["events"][0]


@pytest.mark.asyncio
async def test_numbered_records_aggregate_only_with_explicit_contract():
    text = "\n\n".join(
        f"Paragraph {i + 1}: {('Alpha exact.' if i % 2 else 'Beta exact.') * 100}"
        for i in range(30)
    )
    request, scope = mcp_source(
        text, context_compression_record_format="numbered_paragraphs"
    )
    refs = compact_tool_results(request, scope, ContextCompressionConfig())
    assert refs
    result = await read(request, scope, next(iter(refs)), operation="count_unique")
    assert result["value"] == 2 and result["record_count"] == 30 and result["complete"]
    request, scope = mcp_source(text)
    refs = compact_tool_results(request, scope, ContextCompressionConfig())
    assert refs
    result = await read(request, scope, next(iter(refs)), operation="count_unique")
    assert result["error"] == "unsupported_operation"


@pytest.mark.asyncio
async def test_old_read_pages_become_references_and_remain_retrievable():
    text = "A" * 10000 + "B" * 10000 + "C" * 10000
    request, scope = mcp_source(text)
    config = ContextCompressionConfig()
    refs = compact_tool_results(request, scope, config)
    assert refs
    ref = next(iter(refs))
    for index, offset in enumerate([0, 10000, 20000]):
        result = await read(request, scope, ref, offset=offset)
        event = Event(
            id=f"read-{index}",
            author="agent",
            content=types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=f"r{index}", name=READ_CONTEXT_TOOL, response=result
                        )
                    )
                ],
            ),
        )
        scope.session.events.append(event)
    original = copy.deepcopy(scope.session.events)
    request.contents = [copy.deepcopy(e.content) for e in scope.session.events]
    compact_tool_results(request, scope, config)
    pages = [c.parts[0].function_response.response for c in request.contents[1:]]
    assert pages[0]["text"] == text[:8000]
    assert pages[1]["text"] == text[10000:18000]
    assert pages[0]["archived"] and pages[1]["archived"]
    assert pages[-1]["text"] == "C" * 8000
    assert ref in json.dumps(pages[0])
    again = await read(request, scope, ref, offset=0)
    assert again["text"] == text[:8000]
    assert scope.session.events == original


@pytest.mark.asyncio
async def test_sqlite_reload_can_retrieve_fact_omitted_from_history_summary(tmp_path):
    import re

    from google.adk.models.lite_llm import LiteLLMClient
    from litellm import ModelResponse

    from veadk import Agent, Runner
    from veadk.context.runtime import is_summary
    from veadk.memory.short_term_memory import ShortTermMemory
    from veadk.models.retrying_lite_llm import RetryingLiteLlm

    identity = {
        "app_name": "history_archive",
        "user_id": "user",
        "session_id": "session",
    }
    database = str(tmp_path / "sessions.sqlite3")

    class Client(LiteLLMClient):
        def __init__(self, retrieve=False):
            self.retrieve = retrieve
            self.verified = False

        async def acompletion(self, **kwargs):
            if is_summary.get():
                text = json.dumps(
                    {
                        "goal": "Continue task",
                        "active_constraints": [],
                        "decisions": [],
                        "completed_work": [],
                        "pending_work": [],
                        "evidence": ["Source material was supplied"],
                        "uncertainties": [],
                    }
                )
                message = {"role": "assistant", "content": text}
            elif self.retrieve:
                results = [m for m in kwargs["messages"] if m["role"] == "tool"]
                if results:
                    result = json.loads(results[-1]["content"])
                    assert "ARCHIVED_FACT=4132" in result["text"]
                    self.verified = True
                    message = {"role": "assistant", "content": "4132"}
                else:
                    # The summarizer intentionally omitted this fact.
                    serialized = json.dumps(kwargs["messages"])
                    assert "ARCHIVED_FACT=4132" not in serialized
                    ref = re.search(r"ctx_[a-f0-9]{24}", serialized)[0]
                    message = {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "history-read",
                                "type": "function",
                                "function": {
                                    "name": READ_CONTEXT_TOOL,
                                    "arguments": json.dumps(
                                        {"reference": ref, "query": "ARCHIVED_FACT"}
                                    ),
                                },
                            }
                        ],
                    }
            else:
                message = {"role": "assistant", "content": "Ready"}
            return ModelResponse(model=kwargs["model"], choices=[{"message": message}])

    async def invoke(memory, client, question):
        model = RetryingLiteLlm(
            model="openai/context-test",
            api_key="offline-test",
            llm_client=client,
            context_compression={
                "context_window": 18000,
                "output_reserve": 1000,
                "trigger_ratio": 0.4,
                "summary_trigger_ratio": 0.4,
                "target_ratio": 0.3,
            },
        )
        runner = Runner(
            agent=Agent(name="agent", model=model, model_api_key="offline-test"),
            app_name=identity["app_name"],
            short_term_memory=memory,
        )
        return [
            e
            async for e in runner.run_async(
                user_id="user",
                session_id="session",
                new_message=types.Content(
                    role="user", parts=[types.Part(text=question)]
                ),
            )
        ]

    memory = ShortTermMemory(backend="sqlite", local_database_path=database)
    service = memory.session_service
    session = await service.create_session(**identity)
    for i in range(8):
        for role, text in [
            (
                "user",
                ("ARCHIVED_FACT=4132. " if i == 0 else "") + "Source material. " * 50,
            ),
            ("model", "Recorded. " * 20),
        ]:
            await service.append_event(
                session,
                Event(
                    author="user" if role == "user" else "agent",
                    content=types.Content(role=role, parts=[types.Part(text=text)]),
                ),
            )
    originals = [e.content.model_dump() for e in session.events]
    try:
        await invoke(memory, Client(), "Continue task")
    finally:
        await service.close()
    # Fresh database connection, scope, Runner and model; no in-memory registry.
    memory = ShortTermMemory(backend="sqlite", local_database_path=database)
    try:
        client = Client(retrieve=True)
        await invoke(memory, client, "Retrieve the archived fact")
        assert client.verified
        restored = await memory.session_service.get_session(**identity)
        assert [
            e.content.model_dump() for e in restored.events[: len(originals)]
        ] == originals
    finally:
        await memory.session_service.close()


@pytest.mark.asyncio
async def test_recovered_reference_rejects_foreign_scope_and_modified_source():
    from veadk.context.references import saved_references

    request, scope = mcp_source("X" * 20000)
    refs = compact_tool_results(request, scope, ContextCompressionConfig())
    scope.session.state.update(scope.pending_state)
    fresh = ContextScope(
        session=scope.session.model_copy(deep=True), agent_name="agent", branch=""
    )
    assert saved_references(fresh) == refs
    fresh.session.user_id = "other-user"
    assert saved_references(fresh) == {}
    result = await read(request, fresh, next(iter(refs)))
    assert result["error"] == "context_reference_not_available"
    scope.session.events[0].content.parts[0].function_response.response["content"][0][
        "text"
    ] = "Changed"
    assert (await read(request, scope, next(iter(refs))))[
        "error"
    ] == "context_reference_expired"


@pytest.mark.parametrize(
    "text", ["Paragraph 2: a", "Paragraph 1: a\n\nParagraph 1: b", "[1,2,3]"]
)
def test_count_rejects_undeclared_or_ambiguous_record_semantics(text):
    from veadk.context.operations import count_unique

    with pytest.raises(ValueError):
        count_unique(text, "numbered_paragraphs")


@pytest.mark.asyncio
async def test_search_returns_verbatim_evidence_with_locations_and_budget():
    request, scope = mcp_source(
        "noise " * 4000 + "\nThe comparison baseline is Model-X.\n" + "filler " * 4000
    )
    refs = compact_tool_results(request, scope, ContextCompressionConfig())
    result = await read(
        request,
        scope,
        next(iter(refs)),
        operation="search",
        query="comparison baseline",
    )
    assert result["found"] and not result["complete"]
    original = (
        scope.session.events[0]
        .content.parts[0]
        .function_response.response["content"][0]["text"]
    )
    assert any("Model-X" in item["text"] for item in result["matches"])
    assert sum(len(m["text"].encode()) for m in result["matches"]) <= 8000
    assert all(original[m["offset"] : m["end"]] == m["text"] for m in result["matches"])


@pytest.mark.asyncio
async def test_final_payload_overhead_replans_once_before_delegate(monkeypatch):
    import google.adk.models.lite_llm as adk_model
    from google.adk.models.lite_llm import LiteLLMClient
    from litellm import ModelResponse

    from veadk.context.budget import count_input, resolve_payload_budget
    from veadk.models.retrying_lite_llm import RetryingLiteLlm

    request, scope = mcp_source("x" * 30000)
    # Existing top-level SDK support isolates the final serialization badcase.
    response = scope.session.events[0].content.parts[0].function_response
    response.response = {"result": "x" * 30000}
    request.contents = [copy.deepcopy(scope.session.events[0].content)]
    tool = request.tools_dict["fetch"]
    tool.custom_metadata = {"context_compression_text_fields": ["result"]}
    request.append_tools([tool])
    policy = ContextCompressionConfig(context_window=12000, output_reserve=1000)
    original_convert = adk_model._get_completion_inputs
    conversions, sent = [], []
    framing = None

    async def convert(*args, **kwargs):
        nonlocal framing
        converted = await original_convert(*args, **kwargs)
        messages, tools, schema, params = converted[:4]
        if framing is None:
            payload = {
                "model": "openai/context-test",
                "messages": messages,
                "tools": tools,
            }
            available = resolve_payload_budget(payload, policy).available
            framing = "p" * (available - count_input(payload, policy) + 200)
        messages.append({"role": "system", "content": framing})
        conversions.append(copy.deepcopy(messages))
        return (messages, tools, schema, params, *converted[4:])

    class Client(LiteLLMClient):
        async def acompletion(self, **kwargs):
            assert (
                count_input(kwargs, policy)
                <= resolve_payload_budget(kwargs, policy).available
            )
            sent.append(kwargs)
            return ModelResponse(
                model=kwargs["model"],
                choices=[{"message": {"role": "assistant", "content": "Done"}}],
            )

    monkeypatch.setattr(adk_model, "_get_completion_inputs", convert)
    model = RetryingLiteLlm(
        model="openai/context-test", llm_client=Client(), context_compression=policy
    )
    original_events = copy.deepcopy(scope.session.events)
    token = current_scope.set(scope)
    try:
        _ = [item async for item in model.generate_content_async(request)]
    finally:
        current_scope.reset(token)
    assert len(conversions) == 2 and len(sent) == 1
    assert scope.session.events == original_events


@pytest.mark.asyncio
async def test_explicit_vector_queries_preserve_exact_decimal_results():
    text = json.dumps(
        {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {"metric": {"label": "x" * 5000}, "value": [0, value]}
                    for value in ["0.1", "0.2", "-9.25", "123.456"]
                ],
            },
        }
    )
    request, scope = mcp_source(text, prometheus_vector_queries=True)
    refs = compact_tool_results(request, scope, ContextCompressionConfig())
    for operation, expected in [
        ("count", "4"),
        ("sum", "114.506"),
        ("max", "123.456"),
        ("tail", "123.456"),
    ]:
        result = await read(request, scope, next(iter(refs)), operation=operation)
        assert result["value"] == expected and result["complete"]


@pytest.mark.asyncio
async def test_restore_keeps_unverified_and_protected_reader_evidence():
    from veadk.context.tool_results import restore_fitting_originals

    request, scope = mcp_source("source " * 4000)
    policy = ContextCompressionConfig(protected_context=["PRESERVE_ME"])
    refs = compact_tool_results(request, scope, policy)
    ref = next(iter(refs))
    for i, text in enumerate(["PRESERVE_ME", "unverified evidence"]):
        event = Event(
            author="agent",
            content=types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=READ_CONTEXT_TOOL,
                            id=f"r{i}",
                            response={
                                "reference": ref,
                                "text": text,
                                "source_sha256": refs[ref]["text_hash"],
                            },
                        )
                    )
                ],
            ),
        )
        request.contents.append(copy.deepcopy(event.content))
        if i == 0:
            scope.session.events.append(event)
    originals = copy.deepcopy(request.contents[1:])
    scope.retrieval_calls = 2
    restore_fitting_originals(request, scope, policy, 200000)
    assert request.contents[1:] == originals
    assert (
        request.contents[0].parts[0].function_response.response["content"][0]["text"]
        == "source " * 4000
    )


@pytest.mark.asyncio
async def test_sqlite_multi_step_reader_bounds_projection_and_reloads_tools(tmp_path):
    import re

    from google.adk.agents.run_config import RunConfig
    from google.adk.models.lite_llm import LiteLLMClient
    from litellm import ModelResponse

    from veadk import Agent, Runner
    from veadk.context.budget import count_input, resolve_payload_budget
    from veadk.memory.short_term_memory import ShortTermMemory
    from veadk.models.retrying_lite_llm import RetryingLiteLlm

    source = "Alpha source " * 7000 + "EXACT_END=7319"
    request, _ = mcp_source(source)
    tool = request.tools_dict["fetch"]
    identity = {"app_name": "read_test", "user_id": "user", "session_id": "session"}
    database = str(tmp_path / "tool-session.sqlite3")
    memory = ShortTermMemory(backend="sqlite", local_database_path=database)
    session = await memory.session_service.create_session(**identity)
    contents = [
        types.Content(role="user", parts=[types.Part(text="Load source")]),
        types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        name="fetch", id="fetch-1", args={}
                    )
                )
            ],
        ),
        request.contents[0],
    ]
    for i, content in enumerate(contents):
        await memory.session_service.append_event(
            session,
            Event(
                author="user" if i == 0 else "agent",
                content=content,
                timestamp=1700000000 + i,
            ),
        )
    originals = [e.model_dump() for e in session.events]
    policy = ContextCompressionConfig(context_window=18000, output_reserve=1000)

    observed_pages = {}

    class Client(LiteLLMClient):
        def __init__(self, restarted=False):
            self.calls = 0
            self.restarted = restarted

        async def acompletion(self, **kwargs):
            from veadk.context.runtime import is_summary
            from veadk.context.summary import HistorySummary

            if is_summary.get():
                summary = HistorySummary(
                    goal="Verify source",
                    active_constraints=[],
                    decisions=[],
                    completed_work=[],
                    pending_work=[],
                    evidence=[],
                    uncertainties=[],
                )
                return ModelResponse(
                    model=kwargs["model"],
                    choices=[
                        {
                            "message": {
                                "role": "assistant",
                                "content": summary.model_dump_json(),
                            }
                        }
                    ],
                )
            self.calls += 1
            assert (
                count_input(kwargs, policy)
                <= resolve_payload_budget(kwargs, policy).available
            )
            serialized = json.dumps(kwargs["messages"])
            ref = re.search(r"ctx_[a-f0-9]{24}", serialized)[0]
            pages = [
                json.loads(m["content"])
                for m in kwargs["messages"]
                if m["role"] == "tool" and m.get("tool_call_id", "").startswith("read-")
            ]
            for message in kwargs["messages"]:
                if message["role"] == "tool" and message.get(
                    "tool_call_id", ""
                ).startswith("read-"):
                    page = json.loads(message["content"])
                    if not page.get("archived"):
                        observed_pages[message["tool_call_id"]] = page
            if self.calls > 1:
                assert not pages[-1].get("archived")
                assert all(p.get("archived") for p in pages[:-1])
            if self.calls == (2 if self.restarted else 5):
                if self.restarted:
                    assert "EXACT_END=7319" in pages[-1]["text"]
                message = {"role": "assistant", "content": "Verified"}
            else:
                args = {"reference": ref, "offset": (self.calls - 1) * 3000}
                if self.restarted:
                    args["query"] = "EXACT_END"
                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"read-{self.restarted}-{self.calls}",
                            "type": "function",
                            "function": {
                                "name": READ_CONTEXT_TOOL,
                                "arguments": json.dumps(args),
                            },
                        }
                    ],
                }
            return ModelResponse(model=kwargs["model"], choices=[{"message": message}])

    try:
        for restarted in [False, True]:
            client = Client(restarted)
            model = RetryingLiteLlm(
                model="openai/context-test",
                api_key="offline-test",
                llm_client=client,
                context_compression=policy,
            )
            runner = Runner(
                agent=Agent(
                    name="agent",
                    model=model,
                    model_api_key="offline-test",
                    tools=[tool],
                ),
                app_name=identity["app_name"],
                short_term_memory=memory,
            )
            events = [
                e
                async for e in runner.run_async(
                    user_id="user",
                    session_id="session",
                    new_message=types.Content(
                        role="user", parts=[types.Part(text="Verify source")]
                    ),
                    run_config=RunConfig(max_llm_calls=6),
                )
            ]
            assert events[-1].is_final_response()
            saved = await memory.session_service.get_session(**identity)
            assert [e.model_dump() for e in saved.events[: len(originals)]] == originals
            stored_pages = [
                p.function_response.response
                for e in saved.events
                if e.content
                for p in e.content.parts or []
                if p.function_response and p.function_response.name == READ_CONTEXT_TOOL
            ]
            assert all(not p.get("archived") for p in stored_pages)
            # Pages can shrink before retrieval when input headroom is low.
            # Stored originals must exactly match what the model first saw.
            assert stored_pages == list(observed_pages.values())
            assert all(
                p["text"] == source[p["offset"] : p["end"]] and p["text"]
                for p in stored_pages
            )
            await memory.session_service.close()
            memory = ShortTermMemory(backend="sqlite", local_database_path=database)
    finally:
        await memory.session_service.close()


@pytest.mark.parametrize("raw", ["0e-1000000000", "-0e1000000000"])
def test_zero_exponent_cannot_expand_formatted_statistic(raw):
    from veadk.context.vector_queries import statistic, vector_values

    text = json.dumps(
        {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [{"metric": {}, "value": [0, raw]}],
            },
        }
    )
    # Check the bound first so the pre-fix red test never allocates a huge string.
    value = vector_values(text)[0]
    assert value.as_tuple().exponent == 0
    assert statistic(text, "tail")["value"] == "0"


def test_unrepresentable_decimal_exponent_is_rejected():
    from veadk.context.vector_queries import vector_values

    text = json.dumps(
        {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {"metric": {}, "value": [0, "1e99999999999999999999999999"]}
                ],
            },
        }
    )
    with pytest.raises(ValueError, match="number_limit"):
        vector_values(text)
