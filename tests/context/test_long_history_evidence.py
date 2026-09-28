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

"""Whole-history summary admission must not discard usable retrieved evidence."""

import copy

import pytest
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from veadk.context.budget import ContextBudgetError, count_input, request_payload
from veadk.context.config import ContextCompressionConfig
from veadk.context.history import eligible_prefix_end
from veadk.context.manager import prepare_context
from veadk.context.references import resolve, saved_references
from veadk.context.runtime import current_scope
from test_compression import SummaryClient, content, model_for
from test_hybrid_history import Ranker, scope_for
from test_recoverable_context import read

PIN = "Do not authorize transactions without explicit user approval."
FACT_A = "The historical coverage identifier is CV-7284; expiry date 2031-08-17."
FACT_B = "Correction dated 2026-09-24: coverage now expires 2037-02-19."


def original_history():
    values = []
    for i in range(128):
        values += [
            content("user", f"Historical request {i}. " + "Background topic. " * 12),
            content("model", "Background explanation with no requested detail. " * 24),
        ]
    values[0].parts[0].text = "Retain the first request exactly."
    values[25].parts[0].text += "\n" + FACT_A
    values[89].parts[0].text += "\n" + PIN
    values[191].parts[0].text += "\n" + FACT_B
    values += [content("user", "Find the original coverage identifier.")]
    return values


def policy(budget=12000):
    return ContextCompressionConfig(
        context_window=260000,
        input_limit=budget,
        output_reserve=1024,
        safety_margin=1024,
        verify_sources=False,
        protected_context=(PIN,),
    )


async def prepare(values, ranker, config=None, request_config=None):
    scope = scope_for(values, ranker)
    request = LlmRequest(
        model="openai/context-test",
        contents=copy.deepcopy(values),
        config=request_config or types.GenerateContentConfig(),
    )
    client = SummaryClient()
    token = current_scope.set(scope)
    try:
        await prepare_context(request, model_for(client), config or policy(), {})
    finally:
        current_scope.reset(token)
    return request, scope, client


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [12000, 20000])
async def test_long_history_evidence_reaches_model_without_whole_history_summary(
    budget,
):
    values = original_history()
    before = copy.deepcopy(values)
    config = policy(budget)
    request, scope, client = await prepare(values, Ranker(FACT_A), config)
    assert not client.requests and scope.summary_calls == 0
    rendered = "\n".join(p.text or "" for c in request.contents for p in c.parts)
    assert (
        FACT_A in rendered and PIN in rendered and values[0].parts[0].text in rendered
    )
    end = eligible_prefix_end(values, config.keep_recent_turns)
    assert request.contents[-len(values[end:]) :] == values[end:]
    assert count_input(request_payload(request), config) <= budget
    assert (
        count_input(request_payload(request), config)
        < count_input(request_payload(LlmRequest(contents=values)), config) * 0.2
    )
    assert [event.content for event in scope.session.events] == before == values
    refs = saved_references(scope)
    reference = next(r for r, s in refs.items() if s.get("kind") == "history")
    assert reference in rendered
    source = resolve(scope, refs[reference])
    assert source and FACT_B in source
    # Original facts omitted from the preview still resolve through the actual reader.
    result = await read(
        request, scope, reference, operation="read", offset=source.index(FACT_B)
    )
    assert result["text"].startswith(FACT_B)


@pytest.mark.asyncio
async def test_changed_question_rebuilds_evidence_without_poisoning_summary_cache():
    values = original_history()
    ranker = Ranker(lambda query: FACT_B if "corrected" in query else FACT_A)
    request, scope, client = await prepare(values, ranker)
    assert not client.requests
    first = "\n".join(p.text or "" for c in request.contents for p in c.parts)
    assert FACT_A in first and FACT_B not in first
    assert not any(k.startswith("veadk:context:") for k in scope.pending_state)
    scope.session.state.update(scope.pending_state)
    scope.pending_state.clear()
    next_values = copy.deepcopy(values)
    next_values[-1] = content("user", "Find the corrected coverage expiry.")
    next_request = LlmRequest(model=request.model, contents=next_values)
    token = current_scope.set(scope)
    try:
        await prepare_context(next_request, model_for(client), policy(), {})
    finally:
        current_scope.reset(token)
    after = "\n".join(p.text or "" for c in next_request.contents for p in c.parts)
    assert FACT_B in after and FACT_A not in after
    assert not client.requests and not any(
        k.startswith("veadk:context:") for k in scope.pending_state
    )
    assert [event.content for event in scope.session.events] == values


@pytest.mark.asyncio
async def test_selected_updates_are_rendered_with_original_roles_dates_and_order():
    class Both(Ranker):
        async def rank(self, identity, reference, text, query):
            from veadk.context.history_retrieval import _json

            spans = []
            for fact in (FACT_B, FACT_A):
                literal = _json(fact)[1:-1]
                start = text.index(literal)
                spans.append((start, start + len(literal)))
            return spans

    values = original_history()
    request, _, _ = await prepare(values, Both(FACT_A), policy(20000))
    rendered = request.contents[0].parts[0].text
    assert FACT_A in rendered and FACT_B in rendered
    assert rendered.index(FACT_A) < rendered.index(FACT_B)
    assert "role user" in rendered and "role model" in rendered


@pytest.mark.asyncio
async def test_no_usable_retrieval_keeps_bounded_failure_instead_of_empty_evidence_view():
    class Empty:
        async def rank(self, *args):
            return []

    with pytest.raises(ContextBudgetError) as error:
        await prepare(original_history(), Empty())
    assert error.value.code == "summary_call_budget_exhausted"


@pytest.mark.asyncio
async def test_protected_text_is_never_truncated_to_make_history_fit():
    values = original_history()
    values[89].parts[0].text = PIN + " Protected full detail." * 1400
    before = copy.deepcopy(values)
    with pytest.raises(ContextBudgetError):
        await prepare(values, Ranker(FACT_A))
    assert values == before


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", ["thought", "function"])
async def test_protocol_bearing_history_cannot_be_flattened_into_evidence(protocol):
    values = original_history()
    if protocol == "thought":
        values[101].parts[0].thought = True
    else:
        values[101].parts = [
            types.Part(function_call=types.FunctionCall(name="task", id="c", args={}))
        ]
        values[102].parts = [
            types.Part(
                function_response=types.FunctionResponse(
                    name="task", id="c", response={"ok": True}
                )
            )
        ]
    with pytest.raises(ContextBudgetError):
        await prepare(values, Ranker(FACT_A))


@pytest.mark.asyncio
async def test_full_request_system_and_schema_are_included_in_history_admission():
    values = original_history()
    declaration = types.FunctionDeclaration(
        name="describe",
        description="Business schema must remain complete. " * 30,
        parameters=types.Schema(
            type="OBJECT", properties={"item": types.Schema(type="STRING")}
        ),
    )
    settings = types.GenerateContentConfig(
        system_instruction="System instructions remain exact. " * 100,
        tools=[types.Tool(function_declarations=[declaration])],
    )
    request, _, client = await prepare(values, Ranker(FACT_A), policy(20000), settings)
    assert request.config.system_instruction == settings.system_instruction
    actual = [
        d
        for t in request.config.tools
        for d in t.function_declarations or []
        if d.name == "describe"
    ]
    assert actual == [declaration]
    assert not client.requests
    assert count_input(request_payload(request), policy(20000)) <= 20000


@pytest.mark.asyncio
async def test_source_deleted_during_retrieval_never_creates_an_archived_evidence_view():
    values = original_history()
    scope = scope_for(values, None)

    class Deleted(Ranker):
        async def rank(self, *args):
            spans = await super().rank(*args)
            scope.session.events.clear()
            return spans

    scope.evidence_retriever = Deleted(FACT_A)
    request = LlmRequest(model="openai/context-test", contents=copy.deepcopy(values))
    token = current_scope.set(scope)
    try:
        with pytest.raises(ContextBudgetError):
            await prepare_context(request, model_for(SummaryClient()), policy(), {})
    finally:
        current_scope.reset(token)
    assert not any(
        "Historical evidence view" in (p.text or "")
        for c in request.contents
        for p in c.parts
    )


@pytest.mark.asyncio
async def test_unicode_original_evidence_keeps_exact_characters_and_byte_budget():
    values = original_history()
    fact = 'Historical address: 青川🙂; quoted "name"; two lines:\n编号 CV-7284.'
    values[25].parts[0].text += "\n" + fact
    request, scope, client = await prepare(values, Ranker(fact))
    assert fact in request.contents[0].parts[0].text
    assert not client.requests
    assert count_input(request_payload(request), policy()) <= 12000
    assert [event.content for event in scope.session.events] == values


@pytest.mark.asyncio
async def test_real_runner_one_answer_prefill_and_sqlite_restart_recovers_omitted_original(
    tmp_path,
):
    import json
    from google.adk.events import Event
    from google.adk.models.lite_llm import LiteLLMClient
    from litellm import ModelResponse
    from veadk import Agent, Runner
    from veadk.context.retrieval import use_context_retriever
    from veadk.context.runtime import ContextScope, is_summary
    from veadk.context.tool_results import compact_tool_results
    from veadk.memory.short_term_memory import ShortTermMemory
    from veadk.models.retrying_lite_llm import RetryingLiteLlm

    database = str(tmp_path / "long-history.sqlite3")
    identity = {"app_name": "history", "user_id": "u", "session_id": "s"}
    service = ShortTermMemory(
        backend="sqlite", local_database_path=database
    ).session_service
    session = await service.create_session(**identity)
    values = original_history()[:-1]
    for index, item in enumerate(values):
        await service.append_event(
            session,
            Event(
                id=f"long-{index}",
                timestamp=1700000000 + index,
                author="user" if item.role == "user" else "agent",
                content=copy.deepcopy(item),
            ),
        )
    original_events = copy.deepcopy(session.events)
    await service.close()
    service = ShortTermMemory(
        backend="sqlite", local_database_path=database
    ).session_service
    calls = []

    class Client(LiteLLMClient):
        async def acompletion(self, **kwargs):
            assert not is_summary.get()
            encoded = json.dumps(kwargs["messages"], ensure_ascii=False)
            assert FACT_A in encoded and FACT_B not in encoded and PIN in encoded
            assert "Historical evidence view" in encoded
            request_input = {
                k: kwargs.get(k) for k in ("messages", "tools", "response_format")
            }
            assert count_input(request_input, policy()) <= 12000
            calls.append(True)
            return ModelResponse(
                model=kwargs["model"],
                choices=[
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "CV-7284"},
                    }
                ],
                usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            )

    model = RetryingLiteLlm(
        model="openai/context-test",
        api_key="offline-test",
        llm_client=Client(),
        context_compression=policy(),
    )
    agent = Agent(name="agent", model=model, model_api_key="offline-test")
    runner = Runner(agent=agent, app_name="history", session_service=service)
    try:
        with use_context_retriever(Ranker(FACT_A)):
            answer = await runner.run(
                messages="Find the original coverage identifier.",
                user_id="u",
                session_id="s",
            )
        assert answer == "CV-7284" and len(calls) == 1
        saved = await service.get_session(**identity)
        assert saved.events[: len(original_events)] == original_events
    finally:
        await service.close()
    service = ShortTermMemory(
        backend="sqlite", local_database_path=database
    ).session_service
    try:
        restored = await service.get_session(**identity)
        assert restored.events == saved.events and restored.state == saved.state
        scope = ContextScope(session=restored, agent_name="agent", branch="")
        request = LlmRequest(
            contents=[copy.deepcopy(e.content) for e in restored.events if e.content]
        )
        refs = compact_tool_results(request, scope, policy())
        reference = next(r for r, s in refs.items() if s.get("kind") == "history")
        original_text = resolve(scope, refs[reference])
        result = await read(
            request,
            scope,
            reference,
            operation="read",
            offset=original_text.index(FACT_B),
        )
        assert result["text"].startswith(FACT_B)
        assert restored.events[: len(original_events)] == original_events
        foreign = ContextScope(
            session=restored.model_copy(deep=True), agent_name="agent", branch=""
        )
        foreign.session.user_id = "foreign-user"
        denied = await read(request, foreign, reference, operation="read")
        assert denied["error"] == "context_reference_not_available"
    finally:
        await service.close()
