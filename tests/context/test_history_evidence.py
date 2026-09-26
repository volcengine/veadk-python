"""Preserve original history while avoiding an extra full-history model prefill."""

import copy
import json
from types import SimpleNamespace

import pytest
from google.adk.events import Event
from google.adk.models.lite_llm import LiteLLMClient
from google.adk.models.llm_request import LlmRequest
from google.genai import types
from litellm import ModelResponse

from veadk import Agent, Runner
from veadk.context.config import ContextCompressionConfig
from veadk.context.runtime import ContextScope, current_scope, is_summary
from veadk.context.tool_results import READ_CONTEXT_TOOL, compact_tool_results
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.models.retrying_lite_llm import RetryingLiteLlm


@pytest.mark.asyncio
async def test_history_evidence_uses_one_prefill_and_originals_survive_restart(
    tmp_path,
):
    database = str(tmp_path / "history.sqlite3")
    identity = {"app_name": "history", "user_id": "u", "session_id": "s"}
    memory = ShortTermMemory(backend="sqlite", local_database_path=database)
    service = memory.session_service
    session = await service.create_session(**identity)
    for i in range(4):
        text = "".join(
            f"Archive {i} background note {j}: routine detail.\n" for j in range(90)
        )
        if i == 2:
            text += "The indigo shipment confirmation is CM-4729; preserve this exact code.\n"
        text += "".join(
            f"Archive {i} appendix note {j}: ordinary entry.\n" for j in range(90)
        )
        for role, body in [("user", text), ("model", "Archive received.")]:
            event = Event(
                id=f"{i}-{role}",
                timestamp=1700000000 + i,
                author="user" if role == "user" else "history_agent",
                content=types.Content(role=role, parts=[types.Part(text=body)]),
            )
            await service.append_event(session=session, event=event)
    for i, (role, body) in enumerate(
        [("user", "Keep the archives for the next question."), ("model", "Ready.")]
    ):
        await service.append_event(
            session=session,
            event=Event(
                id=f"tail-{i}",
                timestamp=1700000005 + i,
                author="user" if role == "user" else "history_agent",
                content=types.Content(role=role, parts=[types.Part(text=body)]),
            ),
        )
    await service.close()
    memory = ShortTermMemory(backend="sqlite", local_database_path=database)
    service = memory.session_service
    original = await service.get_session(**identity)
    original_events = copy.deepcopy(original.events)
    calls = []

    class Client(LiteLLMClient):
        async def acompletion(self, **kwargs):
            assert not is_summary.get(), (
                "no full-history summary prefill for this reference lookup"
            )
            text = json.dumps(kwargs.get("messages"), ensure_ascii=False)
            assert "CM-4729" in text
            calls.append(len(text))
            return ModelResponse(
                model="context-test",
                choices=[
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "CM-4729"},
                    }
                ],
                usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            )

    policy = ContextCompressionConfig(
        context_window=30000, input_limit=26000, output_reserve=1024
    )
    model = RetryingLiteLlm(
        model="openai/context-test",
        api_key="offline-test",
        llm_client=Client(),
        context_compression=policy,
    )
    agent = Agent(name="history_agent", model=model, model_api_key="offline-test")
    runner = Runner(agent=agent, app_name="history", session_service=service)
    answer = await runner.run(
        messages="What is the indigo shipment confirmation code?",
        user_id="u",
        session_id="s",
    )
    assert "CM-4729" in answer
    assert (
        len(calls) == 1
        and calls[0] < sum(len(e.content.parts[0].text) for e in original_events) * 0.65
    )
    saved = await service.get_session(**identity)
    assert saved.events[: len(original_events)] == original_events
    await service.close()
    service = ShortTermMemory(
        backend="sqlite", local_database_path=database
    ).session_service
    try:
        restored = await service.get_session(**identity)
        assert restored.events == saved.events and restored.state == saved.state
        scope = ContextScope(session=restored, agent_name="history_agent", branch="")
        request = LlmRequest(
            contents=[copy.deepcopy(e.content) for e in restored.events if e.content]
        )
        refs = compact_tool_results(request, scope, policy)
        ref = next(
            ref for ref, source in refs.items() if source.get("kind") == "history"
        )
        token = current_scope.set(scope)
        try:
            result = await request.tools_dict[READ_CONTEXT_TOOL].func(
                reference=ref,
                tool_context=SimpleNamespace(
                    session=restored, agent_name="history_agent"
                ),
                query="CM-4729",
            )
        finally:
            current_scope.reset(token)
        assert "CM-4729" in result["text"]
        assert restored.events[: len(original_events)] == original_events
    finally:
        await service.close()


def test_short_constraints_assistant_decisions_and_recent_turns_stay_exact():
    from veadk.context.history_projection import project_history

    protected = "Do not send payment. Approval remains pending."
    decision = (
        "Decision: retain CNY 183.47 exactly, including the cancellation condition."
    )
    large = "".join(
        f"Information {i}: unrelated archival material.\n" for i in range(800)
    )
    contents = [
        types.Content(role=role, parts=[types.Part(text=text)])
        for role, text in [
            ("user", protected),
            ("model", decision),
            ("user", large),
            ("model", decision * 50),
            ("user", "What is the payment approval status?"),
        ]
    ]
    original = copy.deepcopy(contents)
    result = project_history(contents, 4, ContextCompressionConfig(), 20000)
    assert result is not None
    projected, _ = result
    for i in (0, 1, 3, 4):
        assert projected[i] == original[i]
    assert contents == original


def test_protected_large_message_and_opaque_protocol_are_not_excerpted():
    from veadk.context.history_projection import project_history

    content = types.Content(
        role="user", parts=[types.Part(text="signed-contract " * 2000 + "KEEP-9382")]
    )
    question = types.Content(role="user", parts=[types.Part(text="Find the contract.")])
    assert (
        project_history(
            [content, question],
            1,
            ContextCompressionConfig(protected_context=("KEEP-9382",)),
            20000,
        )
        is None
    )
    opaque = types.Content(
        role="model",
        parts=[
            types.Part(
                function_call=types.FunctionCall(name="payment", id="p1", args={})
            )
        ],
    )
    assert (
        project_history(
            [content, opaque, question], 2, ContextCompressionConfig(), 20000
        )
        is None
    )


def test_small_budget_preserves_existing_summary_fallback():
    from veadk.context.history_projection import project_history

    contents = [
        types.Content(
            role="user", parts=[types.Part(text="archival information " * 1000)]
        ),
        types.Content(role="user", parts=[types.Part(text="Find archive details.")]),
    ]
    assert project_history(contents, 1, ContextCompressionConfig(), 1000) is None
