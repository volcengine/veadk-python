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
"""Regression tests targeting the seams where VeADK consumes Google ADK APIs
that differ across versions (1.19 vs 2.x).

Scope:
* Direct coverage of every helper in ``veadk.utils.adk_compat`` that the
  pre-existing ``test_adk_compat.py`` did not exercise.
* Edge cases (missing content, empty parts, broken getters) for the event
  function-call/response extraction helpers.
* Consumer-side behavior: every modified call site in runner.py / agent.py /
  ark_llm.py / tool_attributes_extractors.py — including the new defensive
  guards introduced as part of the smooth-upgrade work.
* Real-ADK contract checks: verify the helpers' output matches what the live
  ADK objects produce, so we notice if ADK changes its public surface.

Tests are credential-free: ADK / VeADK constructors that need API keys are
either monkeypatched or constructed with explicit dummy values.
"""

from __future__ import annotations

import importlib
import importlib.metadata as im
from types import SimpleNamespace

import pytest
from packaging.version import Version

import veadk.utils.adk_compat as adk_compat
from veadk.tracing.telemetry.attributes.extractors.tool_attributes_extractors import (
    tool_gen_ai_tool_output,
)
from veadk.tracing.telemetry.attributes.extractors.types import ToolAttributesParams


# ---------------------------------------------------------------------------
# Section A: adk_compat module — direct helpers (15 tests)
#
# These exercise the public surface that ``test_adk_compat.py`` does not yet
# cover: version detection, ``is_adk_gte``, ``should_use_async_db_drivers``,
# ``llm_request_has_field``, and the getter path for
# ``get_event_function_responses`` (the existing file only tests its fallback
# path).
# ---------------------------------------------------------------------------


def test_get_adk_version_returns_version_object():
    """``get_adk_version`` returns a ``packaging.version.Version`` instance."""
    v = adk_compat.get_adk_version()
    assert isinstance(v, Version), f"expected Version, got {type(v).__name__}"


def test_get_adk_version_matches_installed_metadata():
    """``get_adk_version`` agrees with ``importlib.metadata.version``."""
    installed = im.version("google-adk")
    assert str(adk_compat.get_adk_version()) == installed


def test_get_adk_version_is_cached():
    """``get_adk_version`` uses ``lru_cache`` — same identity on repeat calls."""
    assert adk_compat.get_adk_version() is adk_compat.get_adk_version()


def test_is_adk_gte_true_for_lower_target():
    """A version far below current installed should return True."""
    assert adk_compat.is_adk_gte("0.0.1") is True


def test_is_adk_gte_false_for_unreachably_high_target():
    """A version far above current installed should return False."""
    assert adk_compat.is_adk_gte("99.0.0") is False


def test_is_adk_gte_equal_to_current_returns_true():
    """``is_adk_gte`` is inclusive — current installed version compares True."""
    current = str(adk_compat.get_adk_version())
    assert adk_compat.is_adk_gte(current) is True


def test_is_adk_gte_major_only_target_parses():
    """Targets like ``"1"`` or ``"2"`` (major-only) parse and compare cleanly."""
    # Installed is >= 1.19, so "1" must be True.
    assert adk_compat.is_adk_gte("1") is True


def test_should_use_async_db_drivers_true_on_modern_adk():
    """On any ADK >= 1.19 we must select the async DSN scheme."""
    # The whole compat layer assumes >= 1.19, so this must be True on any
    # supported install.
    assert adk_compat.should_use_async_db_drivers() is True


def test_llm_request_has_field_known_field_present():
    """``model`` is a stable LlmRequest field across ADK 1.19 and 2.0."""
    assert adk_compat.llm_request_has_field("model") is True


def test_llm_request_has_field_unknown_field_absent():
    """Unknown field name must return False (no spurious matches)."""
    assert adk_compat.llm_request_has_field("definitely_not_a_real_field_xyz") is False


def test_llm_request_has_field_is_cached():
    """``llm_request_has_field`` uses ``lru_cache`` — repeated calls hit cache."""
    first = adk_compat.llm_request_has_field("model")
    second = adk_compat.llm_request_has_field("model")
    info = adk_compat.llm_request_has_field.cache_info()
    assert first == second is True
    assert info.hits >= 1, "expected at least one cache hit after repeated call"


def test_get_event_function_responses_uses_getter_when_present():
    """When the event exposes ``get_function_responses``, the helper uses it."""
    expected = [SimpleNamespace(name="tool_resp_a")]

    class Event:
        def get_function_responses(self):
            return expected

    assert adk_compat.get_event_function_responses(Event()) == expected


def test_get_event_function_responses_getter_error_falls_back_to_parts():
    """If the getter raises, the helper falls back to ``content.parts``."""

    class Event:
        content = SimpleNamespace(
            parts=[SimpleNamespace(function_response="fallback_resp")]
        )

        def get_function_responses(self):
            raise RuntimeError("getter is broken")

    assert adk_compat.get_event_function_responses(Event()) == ["fallback_resp"]


def test_get_event_function_responses_no_content_returns_empty_list():
    """An event without ``content`` produces an empty list, not an exception."""
    assert adk_compat.get_event_function_responses(SimpleNamespace()) == []


def test_get_event_function_calls_no_content_returns_empty_list():
    """Same shape contract for the function-calls extractor."""
    assert adk_compat.get_event_function_calls(SimpleNamespace()) == []


# ---------------------------------------------------------------------------
# Section B: edge cases for the event extraction helpers (6 tests)
#
# These cover the part-traversal fallback path with awkward shapes that ADK
# may emit in practice: ``parts`` set to ``None``, empty list, or mixed where
# some parts carry a function call/response and others don't.
# ---------------------------------------------------------------------------


def test_get_event_function_calls_empty_parts_returns_empty():
    event = SimpleNamespace(content=SimpleNamespace(parts=[]))
    assert adk_compat.get_event_function_calls(event) == []


def test_get_event_function_calls_parts_none_returns_empty():
    event = SimpleNamespace(content=SimpleNamespace(parts=None))
    assert adk_compat.get_event_function_calls(event) == []


def test_get_event_function_calls_mixed_parts_filters_out_none():
    """Parts without ``function_call`` are skipped; calls are preserved in order."""
    part_a = SimpleNamespace(function_call=SimpleNamespace(name="a"))
    part_b = SimpleNamespace(function_call=None)
    part_c = SimpleNamespace(function_call=SimpleNamespace(name="c"))
    event = SimpleNamespace(content=SimpleNamespace(parts=[part_a, part_b, part_c]))
    calls = adk_compat.get_event_function_calls(event)
    assert [c.name for c in calls] == ["a", "c"]


def test_get_event_function_responses_empty_parts_returns_empty():
    event = SimpleNamespace(content=SimpleNamespace(parts=[]))
    assert adk_compat.get_event_function_responses(event) == []


def test_get_event_function_responses_parts_none_returns_empty():
    event = SimpleNamespace(content=SimpleNamespace(parts=None))
    assert adk_compat.get_event_function_responses(event) == []


def test_get_event_function_responses_mixed_parts_filters_out_none():
    part_a = SimpleNamespace(function_response=SimpleNamespace(name="a"))
    part_b = SimpleNamespace(function_response=None)
    part_c = SimpleNamespace(function_response=SimpleNamespace(name="c"))
    event = SimpleNamespace(content=SimpleNamespace(parts=[part_a, part_b, part_c]))
    responses = adk_compat.get_event_function_responses(event)
    assert [r.name for r in responses] == ["a", "c"]


# ---------------------------------------------------------------------------
# Section C: integration with real ADK Event objects (5 tests)
#
# Verifies that the helpers behave correctly on ADK's actual ``Event``
# instances, not just mocks — guarding against ADK silently changing its
# Event/Content/Part shape across versions.
# ---------------------------------------------------------------------------


def _make_real_adk_text_event(text: str = "hello"):
    from google.adk.events import Event
    from google.genai import types

    return Event(
        invocation_id="inv-1",
        author="user",
        content=types.Content(role="user", parts=[types.Part(text=text)]),
    )


def _make_real_adk_function_call_event():
    from google.adk.events import Event
    from google.genai import types

    fc = types.FunctionCall(name="my_tool", args={"x": 1})
    return Event(
        invocation_id="inv-2",
        author="model",
        content=types.Content(role="model", parts=[types.Part(function_call=fc)]),
    )


def _make_real_adk_function_response_event():
    from google.adk.events import Event
    from google.genai import types

    fr = types.FunctionResponse(name="my_tool", response={"ok": True})
    return Event(
        invocation_id="inv-3",
        author="user",
        content=types.Content(role="user", parts=[types.Part(function_response=fr)]),
    )


def test_real_adk_event_with_text_returns_no_function_calls():
    event = _make_real_adk_text_event()
    assert adk_compat.get_event_function_calls(event) == []
    assert adk_compat.get_event_function_responses(event) == []


def test_real_adk_event_with_function_call_returns_call():
    event = _make_real_adk_function_call_event()
    calls = adk_compat.get_event_function_calls(event)
    assert len(calls) == 1
    assert calls[0].name == "my_tool"


def test_real_adk_event_with_function_response_returns_response():
    event = _make_real_adk_function_response_event()
    responses = adk_compat.get_event_function_responses(event)
    assert len(responses) == 1
    assert responses[0].name == "my_tool"


def test_helper_function_calls_matches_native_getter():
    """Helper output must match ``Event.get_function_calls()`` on real ADK events."""
    event = _make_real_adk_function_call_event()
    assert adk_compat.get_event_function_calls(event) == event.get_function_calls()


def test_helper_function_responses_matches_native_getter():
    event = _make_real_adk_function_response_event()
    assert (
        adk_compat.get_event_function_responses(event) == event.get_function_responses()
    )


# ---------------------------------------------------------------------------
# Section D: Agent.run override gated by ADK version (3 tests)
#
# In ADK 2.0, ``BaseAgent.run`` is a ``@final`` async generator that the
# Workflow engine invokes internally; overriding it breaks NodeRunner. The
# compat fix in ``veadk/agent.py`` only declares the v1 ``NotImplementedError``
# guard when ``not is_adk_gte("2.0.0")``. These tests assert that gating works
# as advertised.
# ---------------------------------------------------------------------------


@pytest.fixture
def _agent_env(monkeypatch):
    """Minimum env needed for ``veadk.Agent()`` to construct without secrets."""
    monkeypatch.setenv("MODEL_AGENT_API_KEY", "dummy-key-for-tests")


def test_agent_remains_subclass_of_adk_llm_agent(_agent_env):
    """VeADK Agent must continue inheriting from ADK's ``LlmAgent``."""
    from google.adk.agents.llm_agent import LlmAgent as ADKLlmAgent

    from veadk import Agent

    assert issubclass(Agent, ADKLlmAgent)


def test_agent_run_override_presence_matches_adk_version(_agent_env):
    """``Agent.run`` should be locally defined on v1.x only.

    On v1.x ``BaseAgent`` has no ``run``, so VeADK declares its own; on v2.x
    the parent ``BaseAgent.run`` is ``@final`` so VeADK must defer to it.
    """
    from veadk import Agent

    has_local_run = "run" in Agent.__dict__
    expected_on_v1 = not adk_compat.is_adk_gte("2.0.0")
    assert has_local_run is expected_on_v1, (
        f"Agent.__dict__ has 'run'={has_local_run}, but expected "
        f"{expected_on_v1} for ADK {adk_compat.get_adk_version()}"
    )


def test_agent_run_raises_notimplemented_on_legacy_adk(_agent_env):
    """On v1.x the override must still surface the deprecation error.

    Skipped automatically on v2.x where the override is intentionally gone.
    """
    if adk_compat.is_adk_gte("2.0.0"):
        pytest.skip("Override is removed on ADK >= 2.0 by design")

    import asyncio

    from veadk import Agent

    agent = Agent(name="t")
    with pytest.raises(NotImplementedError, match="runner.run_async"):
        asyncio.run(agent.run())


# ---------------------------------------------------------------------------
# Section E: ArkLlm version-branching (3 tests)
#
# Covers the version-detection branch in ``ArkLlm.__init__`` (which raises
# ``ImportError`` when ADK lacks ``previous_interaction_id``), plus the
# ``get_previous_interaction_id`` helper applied directly to an LlmRequest.
# ---------------------------------------------------------------------------


def test_arkllm_init_raises_when_field_missing(monkeypatch):
    """If ADK's LlmRequest lacks ``previous_interaction_id``, ArkLlm refuses."""
    monkeypatch.setattr(
        "veadk.models.ark_llm.llm_request_has_field",
        lambda field: False,
    )
    from veadk.models.ark_llm import ArkLlm

    with pytest.raises(ImportError, match="google-adk"):
        ArkLlm(model="ark/test-model")


def test_get_previous_interaction_id_with_real_llm_request():
    """The helper reads cleanly from a real ADK ``LlmRequest`` instance.

    Skipped automatically on ADK versions that do not yet expose the
    ``previous_interaction_id`` field — the whole point of the helper is
    that callers never need to know which version they're on.
    """
    if not adk_compat.llm_request_has_field("previous_interaction_id"):
        pytest.skip("ADK build lacks 'previous_interaction_id' field")

    from google.adk.models.llm_request import LlmRequest

    req = LlmRequest(model="ark/test", previous_interaction_id="iid-42")  # type: ignore[call-arg]
    assert adk_compat.get_previous_interaction_id(req) == "iid-42"


def test_get_previous_interaction_id_returns_none_when_unset():
    """The helper returns ``None`` whether the field is absent or just unset.

    Works on every supported ADK version because it relies only on
    ``getattr(..., default=None)``.
    """
    from google.adk.models.llm_request import LlmRequest

    req = LlmRequest(model="ark/test")
    assert adk_compat.get_previous_interaction_id(req) is None


# ---------------------------------------------------------------------------
# Section F: tool_attributes_extractors fallback variants (4 tests)
#
# After the smooth-upgrade work, ``tool_gen_ai_tool_output`` must accept three
# response object shapes (pydantic-like with ``model_dump``, raw dict, plain
# attribute object) plus an empty list. The existing file tested dict + object
# only; add the model_dump path, the empty-response sentinel, and an id/name
# preservation check.
# ---------------------------------------------------------------------------


def _make_extractor_params(function_response):
    event = SimpleNamespace(
        content=SimpleNamespace(
            parts=[SimpleNamespace(function_response=function_response)]
        )
    )
    return ToolAttributesParams(
        tool=SimpleNamespace(name="my_tool"),
        args={},
        function_response_event=event,
    )


def test_tool_output_extractor_uses_model_dump_when_available():
    """Pydantic-like objects with ``model_dump`` go through the v1 path."""
    response_obj = SimpleNamespace(
        model_dump=lambda: {"id": "fid", "name": "tool_a", "response": {"v": 1}}
    )
    params = _make_extractor_params(response_obj)
    result = tool_gen_ai_tool_output(params)
    assert '"name": "tool_a"' in result.content
    assert '"id": "fid"' in result.content


def test_tool_output_extractor_returns_sentinel_when_no_responses():
    """Empty ``function_responses`` yields the ``<unknown_tool_output>`` sentinel."""
    event = SimpleNamespace(content=SimpleNamespace(parts=[]))
    params = ToolAttributesParams(
        tool=SimpleNamespace(name="my_tool"),
        args={},
        function_response_event=event,
    )
    result = tool_gen_ai_tool_output(params)
    assert "<unknown_tool_output>" in result.content


def test_tool_output_extractor_preserves_id_and_name_for_attribute_object():
    """Falls back to ``getattr`` for objects lacking ``model_dump`` and not dict."""
    response_obj = SimpleNamespace(id="fid_x", name="tool_x", response={"k": "v"})
    result = tool_gen_ai_tool_output(_make_extractor_params(response_obj))
    assert '"id": "fid_x"' in result.content
    assert '"name": "tool_x"' in result.content


def test_tool_output_extractor_handles_missing_attributes_gracefully():
    """An object missing ``id``/``name`` shouldn't crash — getattr default kicks in."""
    response_obj = SimpleNamespace()  # no id, no name, no response
    result = tool_gen_ai_tool_output(_make_extractor_params(response_obj))
    # Should still emit valid JSON content; id/name fall back to empty.
    assert '"id": ""' in result.content
    assert '"name": ""' in result.content


# ---------------------------------------------------------------------------
# Section G: Runner intercept_new_message integration (5 tests)
#
# The runner's ``intercept_new_message`` decorator was updated to (1) route
# through the new ``get_event_function_calls/responses`` helpers and (2)
# tolerate ``part.text is None`` — both are real failure modes when running
# against ADK 2.0's event stream. Drive the wrapper with synthetic event
# streams to confirm.
# ---------------------------------------------------------------------------


@pytest.fixture
def _runner_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_AGENT_API_KEY", "dummy")
    yield


def _make_fake_runner(_runner_env):
    """Build a Runner with a never-called FakeLlm so we can inspect plumbing."""
    from typing import AsyncGenerator

    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse
    from google.genai import types

    from veadk import Agent, Runner
    from veadk.memory.short_term_memory import ShortTermMemory

    class FakeLlm(BaseLlm):
        async def generate_content_async(
            self, llm_request, stream=False
        ) -> AsyncGenerator[LlmResponse, None]:
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part(text="fake reply")],
                )
            )

    agent = Agent(
        name="fake_agent",
        description="fake",
        instruction="be brief",
        model=FakeLlm(model="fake"),
    )
    runner = Runner(agent=agent, short_term_memory=ShortTermMemory(backend="local"))
    return runner


def test_runner_session_service_is_inmemory_for_local_stm(_runner_env):
    """``ShortTermMemory(backend='local')`` plumbs through InMemorySessionService."""
    from google.adk.sessions import InMemorySessionService

    runner = _make_fake_runner(_runner_env)
    assert isinstance(runner.session_service, InMemorySessionService)


@pytest.mark.asyncio
async def test_runner_create_session_returns_adk_session(_runner_env):
    """ADK session-service contract: create_session returns a ``Session``."""
    from google.adk.sessions import Session

    runner = _make_fake_runner(_runner_env)
    session = await runner.session_service.create_session(
        app_name=runner.app_name, user_id="u1", session_id="s1"
    )
    assert isinstance(session, Session)
    assert session.id == "s1"


@pytest.mark.asyncio
async def test_runner_run_async_yields_model_text(_runner_env):
    """End-to-end: an Agent + FakeLlm + Runner yields the model's text event."""
    from google.genai import types

    runner = _make_fake_runner(_runner_env)
    await runner.session_service.create_session(
        app_name=runner.app_name, user_id="u1", session_id="s1"
    )
    msg = types.Content(role="user", parts=[types.Part(text="ping")])
    texts = []
    async for ev in runner.run_async(user_id="u1", session_id="s1", new_message=msg):
        if ev and ev.content and ev.content.parts:
            for p in ev.content.parts:
                if getattr(p, "text", None):
                    texts.append(p.text)
    assert "fake reply" in texts


def _fake_runner_self():
    """Minimum attributes ``pre_run_process`` reads off ``self``."""
    return SimpleNamespace(
        app_name="test_app",
        upload_inline_data_to_tos=False,
        short_term_memory=None,
    )


def _empty_user_message():
    """Empty ``Content`` so ``pre_run_process`` short-circuits cleanly."""
    from google.genai import types

    return types.Content(role="user", parts=[])


async def _no_op_processor(part, app_name, user_id, session_id):
    """Stand-in for ``_upload_image_to_tos`` in the runner wrapper tests."""
    return None


@pytest.mark.asyncio
async def test_runner_intercept_skips_none_events_safely(_runner_env):
    """Synthetic stream containing ``None`` events must not raise."""
    from google.adk.events import Event
    from google.genai import types

    from veadk.runner import intercept_new_message

    async def upstream(**kwargs):
        # Mix valid events with ``None`` to assert the wrapper filters them.
        yield None
        yield Event(
            invocation_id="i",
            author="u",
            content=types.Content(role="user", parts=[types.Part(text="hi")]),
        )

    wrapped = intercept_new_message(_no_op_processor)(upstream)
    collected = []
    async for ev in wrapped(
        _fake_runner_self(),
        user_id="u",
        session_id="s",
        new_message=_empty_user_message(),
    ):
        collected.append(ev)
    # None should be filtered out; the valid event should survive.
    assert len(collected) == 1
    assert collected[0].author == "u"


@pytest.mark.asyncio
async def test_runner_intercept_tolerates_part_text_none(_runner_env):
    """A model event whose ``part.text`` is ``None`` must not raise.

    Regression check for the new ``if part.text and len(part.text.strip()) > 0``
    guard in runner.py — earlier code path called ``.strip()`` on ``None``.
    """
    from google.adk.events import Event
    from google.genai import types

    from veadk.runner import intercept_new_message

    async def upstream(**kwargs):
        yield Event(
            invocation_id="i",
            author="model",
            content=types.Content(
                role="model",
                parts=[types.Part(text=None)],  # the dangerous shape
            ),
        )

    wrapped = intercept_new_message(_no_op_processor)(upstream)
    collected = []
    async for ev in wrapped(
        _fake_runner_self(),
        user_id="u",
        session_id="s",
        new_message=_empty_user_message(),
    ):
        collected.append(ev)
    assert len(collected) == 1


# ---------------------------------------------------------------------------
# Section H: ADK public-surface assumptions (3 tests)
#
# Veadk's compat layer relies on a handful of ADK public modules / classes
# being importable and having stable attributes. These tests guard those
# assumptions so an upstream rename produces a precise, on-topic failure.
# ---------------------------------------------------------------------------


def test_adk_version_module_exposes_version_string():
    """``from google.adk import version; version.__version__`` must be a string."""
    mod = importlib.import_module("google.adk.version")
    assert isinstance(mod.__version__, str)
    assert mod.__version__.split(".")[0].isdigit()


def test_adk_llm_request_model_fields_accessible():
    """The ``model_fields`` introspection used by ``llm_request_has_field`` works."""
    from google.adk.models.llm_request import LlmRequest

    fields = getattr(LlmRequest, "model_fields", None)
    assert isinstance(fields, dict)
    assert "model" in fields, "ADK's LlmRequest must still expose 'model'"


def test_adk_events_module_exports_event_class():
    """``Event`` import path used in runner/evaluator must remain stable."""
    from google.adk.events import Event

    assert hasattr(Event, "get_function_calls")
    assert hasattr(Event, "get_function_responses")
