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

"""Whole-turn contract tests for the Pi runtime.

``test_piagent_runtime.py`` drives single-round Pi streams. The bugs this file
covers are all *multi-round*: they need a turn where the model speaks twice, and
they were invisible to any test that could only express one round.

The context object matters as much as the stream. ``_fake_ctx`` in the sibling
file is a bare ``SimpleNamespace`` with no ``increment_llm_call_count``, and the
runtime reaches that hook through ``getattr(ctx, ..., None)`` -- so a budget test
written against it passes no matter what the runtime does. :func:`_counting_ctx`
supplies a real counter with ADK's semantics instead.
"""

from __future__ import annotations

import json
import stat
from types import SimpleNamespace

import pytest
from google.adk.agents.invocation_context import LlmCallsLimitExceededError
from google.adk.events.event import Event
from google.genai import types

from veadk import Agent
from veadk.runtime.piagent.runtime import PiAgentRuntime
from veadk.runtime.piagent.translate import PiEventTranslator


def _user_event(text: str) -> Event:
    return Event(
        invocation_id="inv-user",
        author="user",
        content=types.Content(role="user", parts=[types.Part(text=text)]),
    )


def _counting_ctx(*events: Event, max_llm_calls: int = 0):
    """A context whose ``increment_llm_call_count`` behaves like ADK's.

    ADK raises once the count *exceeds* the budget, and that raise is what
    ``RunConfig.max_llm_calls`` is made of. A ``SimpleNamespace`` without this
    method makes the runtime's ``getattr`` guard swallow every charge, so a test
    using one cannot tell enforcement from its absence.
    """
    state: dict[str, int] = {"calls": 0}

    def increment_llm_call_count() -> None:
        state["calls"] += 1
        if max_llm_calls and state["calls"] > max_llm_calls:
            raise LlmCallsLimitExceededError(
                f"Max number of llm calls limit of {max_llm_calls} exceeded"
            )

    ctx = SimpleNamespace(
        invocation_id="inv-1",
        session=SimpleNamespace(events=list(events), state={}),
        increment_llm_call_count=increment_llm_call_count,
    )
    ctx.llm_call_state = state
    return ctx


def _make_pi_emitting(tmp_path, lines: list[dict]):
    """A fake Pi binary that replays ``lines`` as NDJSON for one prompt."""
    path = tmp_path / "pi"
    payload = json.dumps(lines)
    path.write_text(
        f"""#!/usr/bin/env python3
import json
import os
import sys

agent_dir = os.environ.get("PI_CODING_AGENT_DIR")
assert agent_dir, "PI_CODING_AGENT_DIR missing"

LINES = json.loads({payload!r})

for raw in sys.stdin:
    command = json.loads(raw)
    if command.get("type") == "prompt":
        print(json.dumps({{
            "id": command.get("id"),
            "type": "response",
            "command": "prompt",
            "success": True,
        }}), flush=True)
        for line in LINES:
            print(json.dumps(line), flush=True)
        break
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _assistant_message(text: str, usage: dict | None = None) -> dict:
    message = {
        "role": "assistant",
        "content": [{"type": "text", "text": text}],
    }
    if usage is not None:
        message["usage"] = usage
    return message


#: A turn where the model writes a preamble alongside its tool call and only
#: answers in round two -- routine model behaviour, and the shape that the
#: `emitted_text` latch got wrong.
_PREAMBLE_THEN_ANSWER = [
    {
        "type": "message_update",
        "assistantMessageEvent": {"type": "text_delta", "delta": "let me check"},
    },
    {
        "type": "tool_execution_start",
        "toolCallId": "call-1",
        "toolName": "get_weather",
        "args": {"city": "Beijing"},
    },
    {
        "type": "tool_execution_end",
        "toolCallId": "call-1",
        "toolName": "get_weather",
        "result": {"weather": "sunny"},
    },
    # Round one closes, re-announcing the preamble the tool-call event carried.
    {"type": "message_end", "message": _assistant_message("let me check")},
    # Round two: the answer.
    {"type": "message_end", "message": _assistant_message("it is sunny")},
    {"type": "agent_settled"},
]


def _agent(**kwargs):
    return Agent(
        name="assistant",
        instruction="Answer briefly.",
        model_name="model-a",
        model_api_base="https://ark.example.com/api/v3/",
        model_api_key="test-key",
        model_api_key_name="",
        runtime="piagent",
        **kwargs,
    )


# ------------------------------------------------- the first-round-wins blocker


@pytest.mark.asyncio
async def test_answer_wins_over_a_tool_call_preamble(tmp_path, monkeypatch) -> None:
    """The round that actually answered must be the turn's answer.

    ``_flush_events`` used to gate on a boolean ``emitted_text`` latch, so the
    first assistant message carrying visible text won for the whole invocation.
    On any turn whose tool call has a text preamble the preamble became the
    answer and the answering round was dropped -- no error, no log, just the
    wrong reply. Buffering alone does not fix it: the buffer simply receives the
    preamble instead.
    """
    binary = _make_pi_emitting(tmp_path, _PREAMBLE_THEN_ANSWER)
    monkeypatch.setenv("PIAGENT_BINARY", str(binary))
    monkeypatch.setenv("PIAGENT_AGENT_DIR", str(tmp_path / "agent-home"))

    ctx = _counting_ctx(_user_event("weather?"))
    events = [e async for e in PiAgentRuntime().run_async(_agent(), ctx)]

    finals = [
        e
        for e in events
        if e.is_final_response() and e.content and e.content.parts
    ]
    assert len(finals) == 1, (
        "a turn must produce exactly one final response; got "
        f"{[[p.text for p in e.content.parts] for e in finals]}"
    )
    text = "".join(p.text or "" for p in finals[0].content.parts)
    assert "it is sunny" in text, (
        f"the answering round was dropped; the turn answered {text!r}"
    )
    assert text.strip() == "it is sunny", (
        f"the preamble leaked into the turn's answer: {text!r}"
    )


# ------------------------------------------------------ the new runtime plumbing


@pytest.mark.asyncio
async def test_max_llm_calls_is_charged_per_model_call(tmp_path, monkeypatch) -> None:
    """Every completed Pi model call must charge ADK's budget.

    Enforcement is one call late by design: Pi owns its loop inside the binary
    and only reports a call once it has finished, so the invocation aborts just
    *past* the limit rather than just short of it. What must not happen is the
    budget never being charged at all -- which is what a context without
    ``increment_llm_call_count`` hides.
    """
    binary = _make_pi_emitting(tmp_path, _PREAMBLE_THEN_ANSWER)
    monkeypatch.setenv("PIAGENT_BINARY", str(binary))
    monkeypatch.setenv("PIAGENT_AGENT_DIR", str(tmp_path / "agent-home"))

    ctx = _counting_ctx(_user_event("weather?"))
    _events = [e async for e in PiAgentRuntime().run_async(_agent(), ctx)]

    assert ctx.llm_call_state["calls"] == 2, (
        "the turn made two backend model calls (two assistant message_end "
        f"events); ADK's budget was charged {ctx.llm_call_state['calls']} times"
    )


@pytest.mark.asyncio
async def test_max_llm_calls_aborts_the_invocation(tmp_path, monkeypatch) -> None:
    """An exhausted budget must abort rather than be swallowed.

    ``LlmCallsLimitExceededError`` is re-raised rather than routed through
    ``on_model_error``, matching ADK: ``Runner`` handles it itself.
    """
    binary = _make_pi_emitting(tmp_path, _PREAMBLE_THEN_ANSWER)
    monkeypatch.setenv("PIAGENT_BINARY", str(binary))
    monkeypatch.setenv("PIAGENT_AGENT_DIR", str(tmp_path / "agent-home"))

    ctx = _counting_ctx(_user_event("weather?"), max_llm_calls=1)

    with pytest.raises(LlmCallsLimitExceededError):
        async for _event in PiAgentRuntime().run_async(_agent(), ctx):
            pass


@pytest.mark.asyncio
async def test_turn_reports_accumulated_token_usage(tmp_path, monkeypatch) -> None:
    """One usage carrier per turn, summed across rounds.

    Consumers add ``usage_metadata`` up across events without deduplicating, so
    a turn must attach it exactly once. Pi reports Anthropic-style *disjoint*
    prompt counters -- ``input`` excludes cached tokens, which arrive separately
    as ``cacheRead``/``cacheWrite`` -- whereas genai's ``prompt_token_count`` is
    the whole prompt with ``cached_content_token_count`` a subset of it. This is
    deliberately not the codex mapping; do not share an assertion helper.
    """
    lines = [
        {
            "type": "message_end",
            "message": _assistant_message(
                "round one",
                usage={"input": 10, "output": 4, "cacheRead": 3, "cacheWrite": 2},
            ),
        },
        {
            "type": "message_end",
            "message": _assistant_message(
                "round two", usage={"input": 5, "output": 6}
            ),
        },
        {"type": "agent_settled"},
    ]
    binary = _make_pi_emitting(tmp_path, lines)
    monkeypatch.setenv("PIAGENT_BINARY", str(binary))
    monkeypatch.setenv("PIAGENT_AGENT_DIR", str(tmp_path / "agent-home"))

    ctx = _counting_ctx(_user_event("hi"))
    events = [e async for e in PiAgentRuntime().run_async(_agent(), ctx)]

    carriers = [e for e in events if getattr(e, "usage_metadata", None) is not None]
    assert len(carriers) == 1, (
        f"expected exactly one usage carrier per turn, got {len(carriers)}"
    )
    usage = carriers[0].usage_metadata
    # prompt <- input + cacheRead + cacheWrite = (10+3+2) + 5
    assert usage.prompt_token_count == 20, usage
    # candidates <- output = 4 + 6
    assert usage.candidates_token_count == 10, usage
    assert usage.cached_content_token_count == 3, usage
    assert usage.total_token_count == 30, usage
    # `reasoning` is a subset of `output` in Pi's accounting, so mapping it onto
    # genai's disjoint `thoughts_token_count` would double-count it.
    assert usage.thoughts_token_count is None, usage


def test_reasoning_tokens_are_never_mapped_to_thoughts() -> None:
    """Unit-level guard for the one mapping that must stay unmapped."""
    translator = PiEventTranslator(author="assistant", invocation_id="inv-1")
    translator.event_to_adk_events(
        {
            "type": "message_end",
            "message": _assistant_message(
                "hi", usage={"input": 8, "output": 5, "reasoning": 4}
            ),
        }
    )
    usage = translator.build_turn_usage_metadata()
    assert usage is not None
    assert usage.prompt_token_count == 8, usage
    assert usage.candidates_token_count == 5, usage
    assert usage.thoughts_token_count is None, (
        "Pi's `reasoning` is a subset of `output`; genai treats thoughts as "
        "disjoint from candidates, so mapping it double-counts"
    )


@pytest.mark.asyncio
async def test_turn_emits_an_indexable_call_llm_span(tmp_path, monkeypatch) -> None:
    """A Pi turn must open the ``call_llm`` span VeADK's telemetry keys off.

    ``_InMemoryExporter`` indexes a session only from spans literally named
    ``call_llm`` carrying ``gen_ai.session.id``; ADK opens that span inside the
    LLM flow this runtime replaces, so without one every Pi trace dump is ``[]``
    and any evaluation built from one raises.

    Driven through a real ``Runner`` rather than :func:`_counting_ctx`: the
    session index is the property that matters, and a ``SimpleNamespace``
    context has no session for the telemetry writer to key off (it fails soft,
    logging ``piagent_trace_call_llm_failed``, which would leave this test
    asserting only that a bare unattributed span exists).
    """
    import uuid

    from google.adk.runners import Runner
    from google.adk.sessions.in_memory_session_service import InMemorySessionService

    from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer

    binary = _make_pi_emitting(
        tmp_path,
        [
            {
                "type": "message_end",
                "message": _assistant_message(
                    "hi", usage={"input": 11, "output": 7}
                ),
            },
            {"type": "agent_settled"},
        ],
    )
    monkeypatch.setenv("PIAGENT_BINARY", str(binary))
    monkeypatch.setenv("PIAGENT_AGENT_DIR", str(tmp_path / "agent-home"))

    # Attaches to whichever provider is already active; deliberately no global
    # TracerProvider swap (ADK's module-level tracers memoize the first real
    # provider they resolve, so replacing it makes later spans vanish).
    tracer = OpentelemetryTracer(exporters=[])
    exporter = tracer._inmemory_exporter._exporter
    before = len(exporter._spans)

    agent = _agent(tracers=[tracer])
    session_id = f"session-{uuid.uuid4().hex[:8]}"
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name="pi", user_id="user", session_id=session_id
    )
    runner = Runner(app_name="pi", agent=agent, session_service=session_service)

    events = [
        event
        async for event in runner.run_async(
            user_id="user",
            session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text="hi")]),
        )
    ]
    assert events, "the pi run produced no events at all"

    spans = exporter._spans[before:]
    call_llm = [s for s in spans if s.name == "call_llm"]
    assert call_llm, f"no call_llm span for a Pi turn: {sorted({s.name for s in spans})}"

    attributes = dict(call_llm[0].attributes or {})
    assert attributes.get("gen_ai.session.id") == session_id, attributes

    # The property the exporter's session index -- and therefore every trace
    # dump and every evaluation built from one -- actually depends on.
    assert exporter.get_finished_spans(session_id), (
        "get_finished_spans() is empty, so OpentelemetryTracer.dump() would "
        "write [] and base_evaluator.build_eval_set would raise"
    )
