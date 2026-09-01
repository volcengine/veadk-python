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

"""Differential ("对拍") matrix: one config, two runtimes, one equivalence class.

Each row runs the *same* agent configuration through ``runtime="adk"`` and
``runtime="codex"`` against the same scripted turn plan, then asserts the two
observable outcomes are equivalent. Rows are split three ways:

``PARITY_ROWS``
    Must produce equivalent observations. A failure here is a real divergence.

``XFAIL_ROWS``
    Divergences ``veadk.runtime.compat`` deliberately classifies as ``warn``:
    accepted, documented, and *still asserted*, with ``strict=True`` so closing
    the gap makes the suite fail until the marker is removed. Turning one of
    these into a plain failure is a one-line change if you would rather see red.

``ERROR_ROWS``
    Configurations ``compat`` classifies as ``error``. Here the contract is the
    refusal itself: constructing the agent must raise a ``ValueError`` that
    names the field, says what would silently break, and offers a way out.

What is deliberately *excluded* from the equivalence class -- reasoning parts,
Codex lifecycle events, ``partial`` deltas, exact event counts, ids/timestamps
-- each carries a paired positive assertion at the bottom of this file. An
exclusion with no paired assertion is a hole, not a simplification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import pytest
from google.adk.agents.invocation_context import LlmCallsLimitExceededError
from google.adk.agents.run_config import RunConfig
from google.adk.examples.base_example_provider import BaseExampleProvider
from google.adk.examples.example import Example
from google.adk.planners.plan_re_act_planner import PlanReActPlanner
from google.adk.tools.long_running_tool import LongRunningFunctionTool
from google.genai import types
from pydantic import BaseModel

from scripted_backend import Round, ScriptedBackend

KB_MARKER = "differential-kb-marker"
EXAMPLE_MARKER = "differential-example-marker"


# ------------------------------------------------------------------- tools


def record_fact(fact: str) -> dict:
    """Record a fact for later."""
    return {"stored": fact}


def lookup_city(city: str) -> dict:
    """Look up a city."""
    return {"city": city, "population": 42}


def slow_approval(request: str) -> dict:
    """A tool whose real work finishes out of band."""
    return {"ticket": request}


class _Examples(BaseExampleProvider):
    def get_examples(self, query: str) -> list[Example]:
        return [
            Example(
                input=types.Content(
                    role="user", parts=[types.Part(text=f"{EXAMPLE_MARKER} question")]
                ),
                output=[
                    types.Content(
                        role="model",
                        parts=[types.Part(text=f"{EXAMPLE_MARKER} answer")],
                    )
                ],
            )
        ]


def _knowledgebase_tool() -> Any:
    """A real ``LoadKnowledgebaseTool`` over a stand-in knowledge base.

    The row is about the *mechanism*: the knowledge base is wired in by
    ``LoadKnowledgebaseTool.process_llm_request``, which the Codex runtime never
    calls, so retrieval is never advertised to the model.
    """
    from types import SimpleNamespace

    from veadk.tools.builtin_tools.load_knowledgebase import LoadKnowledgebaseTool

    return LoadKnowledgebaseTool(
        knowledgebase=SimpleNamespace(
            name=KB_MARKER,
            description="Differential knowledge base.",
            backend="fake",
            enable_profile=False,
        )
    )


class _Answer(BaseModel):
    answer: str


# --------------------------------------------------------------- row types


@dataclass(frozen=True)
class Row:
    """One matrix row: a config, a plan, and what must hold about the pair."""

    id: str
    plan: tuple[Round, ...]
    agent_kwargs: Callable[[ScriptedBackend], dict] | dict = field(default_factory=dict)
    expected_usage: tuple[int, int] | None = None
    run_config: Any = None
    extra_assert: Callable[[Any, Any], None] | None = None
    capture_spans: bool = False
    expect_error: type[BaseException] | None = None


def _kwargs(**values: Any) -> Callable[[ScriptedBackend], dict]:
    return lambda _backend: dict(values)


# ------------------------------------------------------------ extra asserts


def _assert_tool_history_replayed(adk, codex) -> None:
    """The third request must show the model both completed tool round-trips."""
    want = (
        ("function_call", "record_fact"),
        ("function_response", "record_fact"),
        ("function_call", "lookup_city"),
        ("function_response", "lookup_city"),
    )
    assert adk.calls[2].tool_records == want, adk.calls[2].tool_records
    assert codex.calls[2].tool_records == want, codex.calls[2].tool_records


def _assert_output_key_from_session(adk, codex) -> None:
    """``output_key`` is read from the session service, not from the events.

    That is what a downstream ``SequentialAgent`` node actually sees.
    """
    assert adk.session_state.get("answer") == "The sky is blue."
    assert codex.session_state.get("answer") == "The sky is blue."


def _assert_output_key_joins_multi_text(adk, codex) -> None:
    assert adk.session_state.get("answer") == "Part one. Part two."
    assert codex.session_state.get("answer") == "Part one. Part two."


def _assert_temperature_reaches_backend(adk, codex) -> None:
    assert adk.calls[0].temperature == 0.1
    assert codex.calls[0].temperature == 0.1
    assert adk.calls[0].max_output_tokens == 64
    assert codex.calls[0].max_output_tokens == 64


def _assert_no_history_leaks(adk, codex) -> None:
    assert adk.calls[0].history_texts == ()
    assert codex.calls[0].history_texts == ()


def _assert_planner_instruction(adk, codex) -> None:
    for arm in (adk, codex):
        assert "/*PLANNING*/" in arm.calls[0].system_instruction, arm.arm


def _assert_example_reaches_prompt(adk, codex) -> None:
    for arm in (adk, codex):
        assert EXAMPLE_MARKER in arm.calls[0].system_instruction, arm.arm


def _assert_knowledgebase_reaches_prompt(adk, codex) -> None:
    for arm in (adk, codex):
        assert KB_MARKER in arm.calls[0].system_instruction, arm.arm


def _assert_transfer_tool_advertised(adk, codex) -> None:
    for arm in (adk, codex):
        assert "transfer_to_agent" in arm.calls[0].tool_names, arm.arm


def _assert_long_running_marked(adk, codex) -> None:
    for arm in (adk, codex):
        ids = set()
        for event in arm.events:
            ids |= set(getattr(event, "long_running_tool_ids", None) or ())
        assert ids, f"{arm.arm}: no event carried long_running_tool_ids"


def _assert_callbacks_applied(adk, codex) -> None:
    for arm in (adk, codex):
        assert arm.final_text.endswith("[after]"), (arm.arm, arm.final_text)
        assert "[before]" in arm.calls[0].system_instruction, arm.arm


# ---------------------------------------------------------------- the plans


_TEXT_PLAN = (Round(text="The sky is blue.", usage=(10, 4)),)
_TOOL_PLAN = (
    Round(tool_calls=(("record_fact", {"fact": "sky is blue"}),), usage=(0, 0)),
    Round(text="The sky is blue.", usage=(10, 4)),
)
_TWO_TOOL_PLAN = (
    Round(tool_calls=(("record_fact", {"fact": "blue"}),), usage=(0, 0)),
    Round(tool_calls=(("lookup_city", {"city": "Beijing"}),), usage=(0, 0)),
    Round(text="The sky is blue.", usage=(10, 4)),
)
_USAGE_PLAN = (
    Round(tool_calls=(("record_fact", {"fact": "blue"}),), usage=(11, 5)),
    Round(text="The sky is blue.", usage=(7, 3)),
)


def _before_model(callback_context, llm_request):  # noqa: ANN001
    llm_request.append_instructions(["[before]"])
    return None


def _after_model(callback_context, llm_response):  # noqa: ANN001
    parts = list((llm_response.content.parts if llm_response.content else []) or [])
    if parts and parts[-1].text:
        parts[-1] = types.Part(text=parts[-1].text + "[after]")
        llm_response.content = types.Content(role="model", parts=parts)
    return llm_response


PARITY_ROWS: tuple[Row, ...] = (
    Row(id="baseline_text", plan=_TEXT_PLAN, expected_usage=(10, 4)),
    Row(
        id="single_tool",
        plan=_TOOL_PLAN,
        agent_kwargs=_kwargs(tools=[record_fact]),
        expected_usage=(10, 4),
    ),
    Row(
        id="two_tools_sequential",
        plan=_TWO_TOOL_PLAN,
        agent_kwargs=_kwargs(tools=[record_fact, lookup_city]),
        expected_usage=(10, 4),
        extra_assert=_assert_tool_history_replayed,
    ),
    Row(
        id="output_key",
        plan=_TOOL_PLAN,
        agent_kwargs=_kwargs(tools=[record_fact], output_key="answer"),
        expected_usage=(10, 4),
        extra_assert=_assert_output_key_from_session,
    ),
    Row(
        id="output_key_multi_text",
        plan=(Round(texts=("Part one. ", "Part two."), usage=(10, 4)),),
        agent_kwargs=_kwargs(output_key="answer"),
        expected_usage=(10, 4),
        extra_assert=_assert_output_key_joins_multi_text,
    ),
    Row(
        id="before_after_model_callbacks",
        plan=_TEXT_PLAN,
        agent_kwargs=_kwargs(
            before_model_callback=_before_model, after_model_callback=_after_model
        ),
        expected_usage=(10, 4),
        extra_assert=_assert_callbacks_applied,
    ),
    Row(
        id="long_running_tool",
        plan=(
            Round(tool_calls=(("slow_approval", {"request": "deploy"}),), usage=(0, 0)),
            Round(text="The sky is blue.", usage=(10, 4)),
        ),
        agent_kwargs=_kwargs(tools=[LongRunningFunctionTool(func=slow_approval)]),
        expected_usage=(10, 4),
        extra_assert=_assert_long_running_marked,
    ),
    Row(
        id="tracing_spans",
        plan=_TEXT_PLAN,
        expected_usage=(10, 4),
        capture_spans=True,
    ),
    Row(
        id="usage_accounting",
        plan=_USAGE_PLAN,
        agent_kwargs=_kwargs(tools=[record_fact]),
        expected_usage=(18, 8),
    ),
    Row(
        id="max_llm_calls",
        plan=_TWO_TOOL_PLAN,
        agent_kwargs=_kwargs(tools=[record_fact, lookup_city]),
        run_config=RunConfig(max_llm_calls=1),
        expect_error=LlmCallsLimitExceededError,
    ),
)

#: Divergences ``compat.py`` classifies as ``warn``: real, accepted, asserted.
#: ``strict=True`` makes closing one of them fail the suite until the marker is
#: removed, so an accepted gap can never quietly become an unnoticed feature.
XFAIL_ROWS: tuple[tuple[Row, str], ...] = (
    (
        Row(
            id="example_store",
            plan=_TEXT_PLAN,
            agent_kwargs=_kwargs(example_store=_Examples()),
            expected_usage=(10, 4),
            extra_assert=_assert_example_reaches_prompt,
        ),
        "codex never calls ExampleTool.process_llm_request, so few-shot "
        "examples never reach the model (compat.py: warn)",
    ),
    (
        Row(
            id="knowledgebase",
            plan=_TEXT_PLAN,
            agent_kwargs=lambda _b: {"tools": [_knowledgebase_tool()]},
            expected_usage=(10, 4),
            extra_assert=_assert_knowledgebase_reaches_prompt,
        ),
        "codex never calls LoadKnowledgebaseTool.process_llm_request, so the "
        "model is never told the knowledge base exists (compat.py: warn)",
    ),
)

#: Configurations ``compat.py`` refuses outright. The contract is the message.
ERROR_ROWS: tuple[tuple[str, dict, tuple[str, ...]], ...] = (
    (
        "model_object",
        {"model": "sentinel-base-llm"},
        ("Agent(model=", "model_name", "runtime='adk'"),
    ),
    (
        "output_schema",
        {"output_schema": _Answer},
        ("output_schema", "runtime='adk'"),
    ),
    (
        "generate_content_config",
        {
            "generate_content_config": types.GenerateContentConfig(
                temperature=0.1, max_output_tokens=64, stop_sequences=["STOP"]
            )
        },
        ("generate_content_config", "temperature", "silently dropped"),
    ),
    (
        "include_contents_none",
        {"include_contents": "none"},
        ("include_contents", "history", "runtime='adk'"),
    ),
    ("planner", {"planner": PlanReActPlanner()}, ("planner", "runtime='adk'")),
    ("sub_agents", {"sub_agents": "sentinel-sub-agents"}, ("sub_agents", "transfer")),
)


# ------------------------------------------------------------------- tests


async def _run_pair(parity_runner, row: Row):
    adk = await parity_runner.run(
        "adk",
        plan=row.plan,
        agent_kwargs=row.agent_kwargs,
        run_config=row.run_config,
        capture_spans=row.capture_spans,
    )
    codex = await parity_runner.run(
        "codex",
        plan=row.plan,
        agent_kwargs=row.agent_kwargs,
        run_config=row.run_config,
        capture_spans=row.capture_spans,
    )
    return adk, codex


@pytest.mark.asyncio
@pytest.mark.parametrize("row", PARITY_ROWS, ids=lambda row: row.id)
async def test_runtime_parity(parity_runner, compare, row: Row) -> None:
    adk, codex = await _run_pair(parity_runner, row)
    if row.expect_error is not None:
        assert isinstance(adk.error, row.expect_error), adk.error
        assert isinstance(codex.error, row.expect_error), codex.error
        return
    compare(adk, codex, expected_usage=row.expected_usage)
    if row.extra_assert is not None:
        row.extra_assert(adk, codex)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row",
    [
        pytest.param(
            row, id=row.id, marks=pytest.mark.xfail(strict=True, reason=reason)
        )
        for row, reason in XFAIL_ROWS
    ],
)
async def test_runtime_parity_accepted_divergence(
    parity_runner, compare, row: Row
) -> None:
    """Same assertions as :func:`test_runtime_parity`, for known ``warn`` gaps."""
    adk, codex = await _run_pair(parity_runner, row)
    compare(adk, codex, expected_usage=row.expected_usage)
    if row.extra_assert is not None:
        row.extra_assert(adk, codex)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("row_id", "kwargs", "fragments"), ERROR_ROWS, ids=[r[0] for r in ERROR_ROWS]
)
async def test_unsupported_config_fails_fast_and_actionably(
    parity_runner, row_id: str, kwargs: dict, fragments: tuple[str, ...]
) -> None:
    """``compat.py`` must refuse, name the field, and offer a way out.

    A silent no-op is the failure mode this whole suite exists to prevent; a
    refusal is only useful if its message tells the caller what to do instead.
    """
    from veadk import Agent

    resolved = dict(kwargs)
    if resolved.get("model") == "sentinel-base-llm":
        resolved["model"] = ScriptedBackend([Round(text="x")]).as_base_llm()
    if resolved.get("sub_agents") == "sentinel-sub-agents":
        resolved["sub_agents"] = [
            Agent(name="specialist", model_name="scripted-model", model_api_key="k")
        ]

    with pytest.raises(ValueError) as excinfo:
        Agent(
            name="parity_agent",
            model_name="scripted-model",
            model_api_base="https://backend.invalid/v1",
            model_api_key="backend-key",
            runtime="codex",
            **resolved,
        )
    message = str(excinfo.value)
    for fragment in fragments:
        assert fragment in message, f"{row_id}: {fragment!r} missing from {message!r}"


# -------------------------------------------------- paired positive asserts
#
# Every entry in the excluded set above is only safe to exclude because one of
# these pins the property that made it safe to ignore.


@pytest.mark.asyncio
async def test_excluded_reasoning_parts_are_thoughts_and_never_reach_output_key(
    parity_runner,
) -> None:
    """Paired with: reasoning/thought parts are excluded from the comparison."""
    from google.adk.events.event import Event

    from veadk.runtime.codex.translate import item_to_events
    from veadk.runtime.output_state import maybe_save_output_to_state

    events = item_to_events(
        {"id": "r1", "type": "reasoning", "summary": [{"text": "thinking hard"}]},
        "parity_agent",
        "inv",
    )
    assert events, "a reasoning item must still be observable"
    part = events[0].content.parts[0]
    assert part.thought is True
    assert part.text == "thinking hard"

    from types import SimpleNamespace

    agent = SimpleNamespace(
        name="parity_agent", output_key="answer", output_schema=None
    )
    for event in events:
        assert isinstance(event, Event)
        maybe_save_output_to_state(agent, event)
        assert event.actions.state_delta == {}


@pytest.mark.asyncio
async def test_excluded_codex_lifecycle_events_exist_and_carry_turn_id(
    parity_runner,
) -> None:
    """Paired with: Codex lifecycle events are excluded from the comparison."""
    codex = await parity_runner.run("codex", plan=_TEXT_PLAN)
    assert codex.error is None, codex.error

    lifecycle = [
        event
        for event in codex.events
        if (event.custom_metadata or {}).get("codex_event_type")
    ]
    assert lifecycle, "the codex arm produced no lifecycle events at all"
    by_type = {
        (event.custom_metadata or {})["codex_event_type"]: event for event in lifecycle
    }
    assert "turn_started" in by_type
    assert "turn_complete" in by_type
    assert by_type["turn_started"].custom_metadata["turn_id"] == "turn-1"
    assert by_type["turn_complete"].custom_metadata["turn_id"] == "turn-1"


@pytest.mark.asyncio
async def test_excluded_partial_deltas_precede_their_completed_item(
    parity_runner,
) -> None:
    """Paired with: ``partial=True`` deltas are excluded from the comparison."""
    codex = await parity_runner.run("codex", plan=_TEXT_PLAN)
    assert codex.error is None, codex.error

    delta_at = next(
        (
            index
            for index, event in enumerate(codex.events)
            if (event.custom_metadata or {}).get("codex_event_type") == "message_delta"
        ),
        None,
    )
    completed_at = next(
        (
            index
            for index, event in enumerate(codex.events)
            if (event.custom_metadata or {}).get("codex_event_type") == "item_completed"
        ),
        None,
    )
    assert delta_at is not None, "no streaming delta was emitted"
    assert completed_at is not None, "no completed item was emitted"
    assert delta_at < completed_at
    assert codex.events[delta_at].partial is True


@pytest.mark.asyncio
async def test_codex_arm_really_drove_the_shim_over_http(parity_runner) -> None:
    """The fake is not allowed to shortcut the shim.

    If this ever passes with an empty request log, the codex arm has silently
    stopped exercising ``proxy._synth_sse`` and every row above is testing a
    much smaller system than it claims to.
    """
    import fake_codex_sdk

    codex = await parity_runner.run(
        "codex", plan=_TOOL_PLAN, agent_kwargs=_kwargs(tools=[record_fact])
    )
    assert codex.error is None, codex.error
    assert fake_codex_sdk.REQUEST_LOG, "the codex arm never POSTed to the shim"
    assert all(body["stream"] is True for body in fake_codex_sdk.REQUEST_LOG)


def test_plain_codex_agent_constructs_without_tripping_the_model_rule() -> None:
    """The fail-fast layer must not fire on an ordinary codex agent.

    ``model_post_init`` assigns ``self.model`` itself, so a rule keyed on raw
    ``model_fields_set`` would make the ``model`` ERROR fire for *every* codex
    agent. ``Agent`` snapshots ``frozenset(self.model_fields_set)`` into
    ``_veadk_explicit_fields`` at the top of ``model_post_init`` to distinguish
    "the caller passed it" from "we assigned it".
    """
    from veadk import Agent
    from veadk.runtime.compat import explicit_fields

    agent = Agent(
        name="plain_codex_agent",
        model_name="scripted-model",
        model_api_base="https://backend.invalid/v1",
        model_api_key="backend-key",
        runtime="codex",
    )

    assert agent.model, "model_post_init should still have built a client"
    explicit = explicit_fields(agent)
    assert "model" not in explicit, explicit
    assert "model_extra_config" not in explicit, explicit
    assert "model_name" in explicit


def test_explicit_field_snapshot_survives_clone() -> None:
    """``BaseAgent.clone()`` re-``setattr``s list fields, widening fields_set.

    Without the snapshot surviving the clone, a per-request clone of a valid
    codex agent would start failing the ``model`` / ``model_extra_config``
    rules that the original passed.
    """
    from veadk import Agent
    from veadk.runtime.compat import check_agent_runtime_support, explicit_fields

    agent = Agent(
        name="clonable_codex_agent",
        model_name="scripted-model",
        model_api_base="https://backend.invalid/v1",
        model_api_key="backend-key",
        runtime="codex",
    )
    clone = agent.clone()

    assert explicit_fields(clone) == explicit_fields(agent)
    # The real contract: the clone still validates.
    check_agent_runtime_support(clone, "codex")
