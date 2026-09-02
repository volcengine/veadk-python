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

"""Meta-tests: prove the differential harness can fail.

A comparison harness that cannot detect a divergence turns every row in
``test_runtime_parity.py`` permanently green, which is strictly worse than
having no suite at all. These tests inject known faults into the Codex arm and
assert the comparison raises for each of them.

They are deliberately the first thing in the suite: written before the matrix,
and the first thing to check when a parity row unexpectedly goes green.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from google.adk.events.event import Event
from google.genai import types

import conftest as harness  # noqa: F401  (documented below)
from scripted_backend import RecordedCall, Round, ScriptedBackend

# The tool round declares zero tokens on purpose. The Codex arm reports only
# the *final* backend response's usage (the shim's internal tool loop does not
# accumulate across rounds -- see the `usage_accounting` row in
# ``test_runtime_parity.py``), and these meta-tests must fail only because of
# the fault they inject, never because of an unrelated known divergence.
_PLAN = [
    Round(tool_calls=(("record_fact", {"fact": "sky is blue"}),), usage=(0, 0)),
    Round(text="The sky is blue.", usage=(10, 4)),
]


def record_fact(fact: str) -> dict:
    """Record a fact."""
    return {"stored": fact}


def _agent_kwargs(_backend: ScriptedBackend) -> dict:
    return {"tools": [record_fact], "output_key": "answer"}


async def _both(parity_runner, **kwargs):
    adk = await parity_runner.run("adk", plan=_PLAN, agent_kwargs=_agent_kwargs)
    codex = await parity_runner.run(
        "codex", plan=_PLAN, agent_kwargs=_agent_kwargs, **kwargs
    )
    return adk, codex


# ------------------------------------------------------------- fault matrix


def _drop_tool_call(outcome) -> None:
    outcome.tool_calls = ()
    outcome.tool_responses = ()


def _drop_state_delta(outcome) -> None:
    outcome.state_delta = {}
    outcome.session_state = {}


def _different_text(outcome) -> None:
    outcome.final_text = "something else entirely"


def _zero_usage(outcome) -> None:
    outcome.usage = (0, 0, 0)


def _drop_request(outcome) -> None:
    outcome.calls = outcome.calls[:1]


def _drop_temperature(outcome) -> None:
    outcome.calls = [
        RecordedCall(**{**call.__dict__, "temperature": None}) for call in outcome.calls
    ]


def _drop_history(outcome) -> None:
    outcome.calls = [
        RecordedCall(**{**call.__dict__, "history_texts": ()}) for call in outcome.calls
    ]


def _drop_tool_history(outcome) -> None:
    outcome.calls = [
        RecordedCall(**{**call.__dict__, "tool_records": ()}) for call in outcome.calls
    ]


def _drop_event_kind(outcome) -> None:
    outcome.event_kinds = frozenset()


def _drop_spans(outcome) -> None:
    outcome.span_names = frozenset({"invocation"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        pytest.param(_drop_tool_call, id="drops_tool_call"),
        pytest.param(_drop_state_delta, id="drops_state_delta"),
        pytest.param(_different_text, id="different_text"),
        pytest.param(_zero_usage, id="zero_usage"),
        pytest.param(_drop_request, id="drops_a_request"),
        pytest.param(_drop_temperature, id="drops_temperature"),
        pytest.param(_drop_history, id="drops_history"),
        pytest.param(_drop_tool_history, id="drops_tool_history"),
        pytest.param(_drop_event_kind, id="drops_event_kind"),
    ],
)
async def test_harness_detects_injected_divergence(
    parity_runner, compare, fault
) -> None:
    """Each injected fault must make the comparison raise."""
    adk, codex = await _both(parity_runner, codex_fault=fault)
    assert adk.error is None, adk.error
    assert codex.error is None, codex.error

    # A fault on temperature/history only shows up if the un-faulted values
    # differ from the ADK arm's, so seed the ADK side with a real value first.
    if fault is _drop_temperature:
        adk.calls = [
            RecordedCall(**{**call.__dict__, "temperature": 0.1}) for call in adk.calls
        ]
    if fault is _drop_history:
        adk.calls = [
            RecordedCall(**{**call.__dict__, "history_texts": ("earlier",)})
            for call in adk.calls
        ]
    if fault is _drop_tool_history:
        seeded = (("function_call", "record_fact"),)
        adk.calls = [
            RecordedCall(**{**call.__dict__, "tool_records": seeded})
            for call in adk.calls
        ]

    with pytest.raises(AssertionError, match="runtime parity mismatch"):
        compare(adk, codex, expected_usage=(10, 4))


@pytest.mark.asyncio
async def test_harness_detects_span_divergence(parity_runner, compare) -> None:
    """Spans are compared only when both arms captured them -- and then it bites."""
    adk, codex = await _both(parity_runner)
    adk.span_names = frozenset({"invocation", "call_llm"})
    codex.span_names = frozenset({"invocation"})

    with pytest.raises(AssertionError, match="call_llm"):
        compare(adk, codex)


@pytest.mark.asyncio
async def test_harness_detects_declared_usage_shortfall(parity_runner, compare) -> None:
    """``expected_usage`` pins the plan's exact total, not merely "non-zero"."""
    adk, codex = await _both(parity_runner)

    with pytest.raises(AssertionError, match="plan declares"):
        compare(adk, codex, expected_usage=(999, 999))


@pytest.mark.asyncio
async def test_harness_detects_error_type_divergence(parity_runner, compare) -> None:
    """An exception in one arm and not the other is itself a divergence."""
    adk, codex = await _both(parity_runner)
    codex.error = RuntimeError("boom")

    with pytest.raises(AssertionError, match="error type"):
        compare(adk, codex)


@pytest.mark.asyncio
async def test_unfaulted_run_compares_equal(parity_runner, compare) -> None:
    """The control: without an injected fault the two arms agree.

    Without this, every ``pytest.raises`` above could be passing for the wrong
    reason (a harness that always raises).
    """
    adk, codex = await _both(parity_runner)
    assert adk.error is None, adk.error
    assert codex.error is None, codex.error
    compare(adk, codex, expected_usage=(10, 4))


# ------------------------------------------------- closed-allowlist guarding


def test_classifier_rejects_an_event_it_cannot_classify(event_classifier) -> None:
    """An unclassifiable event raises rather than being silently dropped.

    This is what forces a human decision when the Codex SDK grows a new
    notification type: the alternative -- dropping it -- would quietly shrink
    the equivalence class.
    """
    mystery = SimpleNamespace(
        partial=False,
        content=None,
        error_code=None,
        custom_metadata=None,
        actions=None,
    )
    with pytest.raises(AssertionError, match="unclassified event"):
        event_classifier(mystery)


def test_classifier_rejects_an_unknown_codex_lifecycle_type(event_classifier) -> None:
    mystery = SimpleNamespace(
        partial=False,
        content=None,
        error_code=None,
        custom_metadata={"codex_event_type": "brand_new_notification"},
        actions=None,
    )
    with pytest.raises(AssertionError, match="unclassified codex lifecycle"):
        event_classifier(mystery)


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        pytest.param(
            Event(
                invocation_id="inv",
                author="a",
                content=types.Content(role="model", parts=[types.Part(text="hi")]),
            ),
            "text",
            id="text",
        ),
        pytest.param(
            Event(
                invocation_id="inv",
                author="a",
                partial=True,
                content=types.Content(role="model", parts=[types.Part(text="h")]),
            ),
            "delta",
            id="delta",
        ),
        pytest.param(
            Event(
                invocation_id="inv",
                author="a",
                content=types.Content(
                    role="model", parts=[types.Part(text="why", thought=True)]
                ),
            ),
            "thought",
            id="thought",
        ),
        pytest.param(
            Event(
                invocation_id="inv",
                author="a",
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(id="c", name="t", args={})
                        )
                    ],
                ),
            ),
            "function_call",
            id="function_call",
        ),
        pytest.param(
            Event(
                invocation_id="inv",
                author="a",
                content=types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                id="c", name="t", response={}
                            )
                        )
                    ],
                ),
            ),
            "function_response",
            id="function_response",
        ),
        pytest.param(
            Event(
                invocation_id="inv",
                author="a",
                custom_metadata={"codex_event_type": "turn_complete"},
                turn_complete=True,
            ),
            "codex_lifecycle",
            id="lifecycle",
        ),
        pytest.param(
            Event(
                invocation_id="inv",
                author="a",
                error_code="backend",
                error_message="nope",
            ),
            "error",
            id="error",
        ),
    ],
)
def test_classifier_vocabulary(event_classifier, event, expected) -> None:
    assert event_classifier(event) == expected


# ------------------------------------------- the backend records its inputs


def test_fake_codex_prompt_text_accepts_sdk_and_stub_shapes() -> None:
    StubTextInput = type("TextInput", (), {})
    stub = StubTextInput()
    stub.value = "from stub"

    SdkTextInput = type("TextInput", (), {})
    sdk = SdkTextInput()
    sdk.text = "from sdk"

    assert harness.fake_codex_sdk._prompt_text([stub, sdk]) == "from stub\nfrom sdk"


@pytest.mark.asyncio
async def test_recorded_call_is_shaped_the_same_in_both_arms(parity_runner) -> None:
    """The normalizer really does make two different protocols comparable.

    Without this, ``RecordedCall`` equality could be trivially satisfied by two
    arms that both record nothing.
    """
    adk, codex = await _both(parity_runner)
    assert adk.calls and codex.calls
    assert adk.calls[0].current_text == "do the thing"
    assert codex.calls[0].current_text == "do the thing"
    assert adk.calls[0].tool_names == ("record_fact",)
    assert codex.calls[0].tool_names == ("record_fact",)
    # The second request must show the model its own tool history.
    assert adk.calls[1].tool_records == (
        ("function_call", "record_fact"),
        ("function_response", "record_fact"),
    )
    assert codex.calls[1].tool_records == adk.calls[1].tool_records
