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

"""Differential ("对拍") harness: run one agent config through both runtimes.

The suite's whole value rests on the comparison actually being able to fail, so
three mechanisms guard it:

1. :func:`normalize_events` is a **closed allowlist**. An event it cannot
   classify raises instead of being dropped, so a new Codex event type forces a
   human decision rather than silently widening the excluded set.
2. Every exclusion carries a paired positive assertion somewhere in the suite
   (see ``test_runtime_parity.py``'s "paired positive" tests).
3. ``test_parity_harness.py`` injects faults into the Codex arm and asserts the
   comparison raises for each.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

import pytest
from google.genai import types

import fake_codex_sdk
import scripted_backend
from scripted_backend import RecordedCall, Round, ScriptedBackend

#: Event classifications deliberately kept out of the equivalence class. Each
#: one has a paired positive assertion in ``test_runtime_parity.py``.
EXCLUDED_KINDS = frozenset({"thought", "delta", "codex_lifecycle", "adk_state"})

#: The comparable event vocabulary.
COMPARED_KINDS = frozenset({"text", "function_call", "function_response"})

_CODEX_LIFECYCLE_TYPES = frozenset(
    {
        "item_started",
        "item_completed",
        "message_delta",
        "command_output",
        "file_change_output",
        "mcp_progress",
        "plan_delta",
        "reasoning_delta",
        "file_change_patch",
        "plan_item",
        "plan_update",
        "turn_started",
        "turn_complete",
        "token_usage",
        "approval_review",
        "context_compacted",
        "model_rerouted",
        "error",
    }
)


@dataclass
class RunOutcome:
    """Everything one arm produced, normalized for comparison."""

    arm: str
    final_text: str = ""
    tool_calls: tuple[tuple[str, str], ...] = ()
    tool_responses: tuple[str, ...] = ()
    state_delta: dict[str, Any] = field(default_factory=dict)
    session_state: dict[str, Any] = field(default_factory=dict)
    usage: tuple[int, int, int] = (0, 0, 0)
    event_kinds: frozenset[str] = frozenset()
    span_names: frozenset[str] | None = None
    calls: list[RecordedCall] = field(default_factory=list)
    events: list[Any] = field(default_factory=list)
    authors: tuple[str, ...] = ()
    declared_usage: tuple[int, int] = (0, 0)
    error: BaseException | None = None


def classify_event(event: Any) -> str:
    """Classify one ADK event. Raises on anything the suite has not seen.

    This is the closed allowlist. Widening it is a deliberate act.
    """
    if getattr(event, "partial", False):
        return "delta"

    content = getattr(event, "content", None)
    parts = list(getattr(content, "parts", None) or []) if content else []
    parts = [p for p in parts if p is not None]
    if parts:
        if any(
            getattr(p, "text", None) is not None and getattr(p, "thought", False)
            for p in parts
        ):
            return "thought"
        if any(getattr(p, "function_call", None) is not None for p in parts):
            return "function_call"
        if any(getattr(p, "function_response", None) is not None for p in parts):
            return "function_response"
        if any(getattr(p, "text", None) is not None for p in parts):
            return "text"

    if getattr(event, "error_code", None):
        return "error"

    metadata = getattr(event, "custom_metadata", None) or {}
    codex_type = metadata.get("codex_event_type")
    if codex_type is not None:
        if codex_type not in _CODEX_LIFECYCLE_TYPES:
            raise AssertionError(
                f"unclassified codex lifecycle event type {codex_type!r}: {event!r}"
            )
        return "codex_lifecycle"

    actions = getattr(event, "actions", None)
    if actions is not None and content is None:
        return "adk_state"

    raise AssertionError(f"unclassified event: {event!r}")


def normalize_events(events: Sequence[Any], agent_name: str) -> dict[str, Any]:
    """Reduce a raw event stream to the comparable observables."""
    kinds: set[str] = set()
    texts: list[str] = []
    tool_calls: list[tuple[str, str]] = []
    tool_responses: list[str] = []
    state_delta: dict[str, Any] = {}
    prompt = candidates = total = 0

    for event in events:
        kind = classify_event(event)
        if kind in COMPARED_KINDS:
            kinds.add(kind)

        usage = getattr(event, "usage_metadata", None)
        if usage is not None:
            prompt += int(getattr(usage, "prompt_token_count", 0) or 0)
            candidates += int(getattr(usage, "candidates_token_count", 0) or 0)
            total += int(getattr(usage, "total_token_count", 0) or 0)

        actions = getattr(event, "actions", None)
        if actions is not None:
            state_delta.update(dict(getattr(actions, "state_delta", None) or {}))

        content = getattr(event, "content", None)
        parts = [p for p in (getattr(content, "parts", None) or []) if p is not None]
        if kind == "text":
            texts.extend(
                str(p.text)
                for p in parts
                if getattr(p, "text", None) and not getattr(p, "thought", False)
            )
        elif kind == "function_call":
            for part in parts:
                call = getattr(part, "function_call", None)
                if call is not None and call.name:
                    # Compare by value, never by author: codex's item_to_events
                    # uses role "user" for tool responses.
                    tool_calls.append((str(call.name), _stable(call.args or {})))
        elif kind == "function_response":
            for part in parts:
                response = getattr(part, "function_response", None)
                if response is not None and response.name:
                    tool_responses.append(str(response.name))

    return {
        "kinds": frozenset(kinds),
        "final_text": "".join(texts).strip(),
        "tool_calls": tuple(tool_calls),
        "tool_responses": tuple(tool_responses),
        "state_delta": state_delta,
        "usage": (prompt, candidates, total),
    }


def _stable(value: Any) -> str:
    import json

    try:
        return json.dumps(value, sort_keys=True, default=str)
    except Exception:  # noqa: BLE001
        return str(value)


# --------------------------------------------------------------- comparison


def compare_runs(
    adk: RunOutcome,
    codex: RunOutcome,
    *,
    expected_usage: tuple[int, int] | None = None,
) -> None:
    """Assert the two arms are in the same equivalence class.

    Every mismatch is collected before raising, so one systemic divergence
    (e.g. missing spans) cannot mask the others.
    """
    problems: list[str] = []

    def check(label: str, left: Any, right: Any) -> None:
        if left != right:
            problems.append(f"{label}: adk={left!r} codex={right!r}")

    if type(adk.error) is not type(codex.error):
        problems.append(
            f"error type: adk={type(adk.error).__name__} "
            f"codex={type(codex.error).__name__}"
        )
    if adk.error is not None or codex.error is not None:
        if problems:
            raise AssertionError("runtime parity mismatch:\n  " + "\n  ".join(problems))
        return

    check("final_text", adk.final_text, codex.final_text)
    check("tool_calls", adk.tool_calls, codex.tool_calls)
    check("tool_responses", adk.tool_responses, codex.tool_responses)
    check("state_delta", adk.state_delta, codex.state_delta)
    check("session_state(output_key)", adk.session_state, codex.session_state)

    if not adk.event_kinds <= codex.event_kinds:
        problems.append(
            f"event kinds: adk {sorted(adk.event_kinds)} not a subset of "
            f"codex {sorted(codex.event_kinds)}"
        )

    if expected_usage is not None:
        want = (expected_usage[0], expected_usage[1], sum(expected_usage))
        if adk.usage != want:
            problems.append(f"adk usage: got {adk.usage}, plan declares {want}")
        if codex.usage != want:
            problems.append(f"codex usage: got {codex.usage}, plan declares {want}")

    if adk.span_names is not None and codex.span_names is not None:
        if not adk.span_names <= codex.span_names:
            problems.append(
                f"span names: adk {sorted(adk.span_names)} not a subset of "
                f"codex {sorted(codex.span_names)}"
            )
        for arm, names in (("adk", adk.span_names), ("codex", codex.span_names)):
            if "call_llm" not in names:
                problems.append(f"{arm} spans missing call_llm: {sorted(names)}")

    for index, (left, right) in enumerate(zip(adk.calls, codex.calls)):
        if left.comparable() != right.comparable():
            for key, value in left.comparable().items():
                other = right.comparable()[key]
                if value != other:
                    problems.append(
                        f"request[{index}].{key}: adk={value!r} codex={other!r}"
                    )
    if len(adk.calls) != len(codex.calls):
        problems.append(f"request count: adk={len(adk.calls)} codex={len(codex.calls)}")

    if problems:
        raise AssertionError("runtime parity mismatch:\n  " + "\n  ".join(problems))


# ------------------------------------------------------------------ running


class ParityRunner:
    """Runs one agent configuration through one runtime, offline."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.monkeypatch = monkeypatch

    async def run(
        self,
        arm: str,
        *,
        plan: Iterable[Round],
        agent_kwargs: Callable[[ScriptedBackend], dict] | dict | None = None,
        run_config: Any = None,
        capture_spans: bool = False,
        codex_fault: Callable[[RunOutcome], None] | None = None,
        user_text: str = "do the thing",
        session_id: str | None = None,
    ) -> RunOutcome:
        from google.adk.runners import Runner
        from google.adk.sessions.in_memory_session_service import InMemorySessionService

        from veadk import Agent
        from veadk.runtime import get_runtime

        get_runtime.cache_clear()
        backend = ScriptedBackend(plan, arm=arm)
        kwargs = dict(
            agent_kwargs(backend) if callable(agent_kwargs) else (agent_kwargs or {})
        )
        agent_name = kwargs.pop("name", "parity_agent")
        session_id = session_id or f"session-{uuid.uuid4().hex[:8]}"

        tracer = None
        spans_before = 0
        if capture_spans:
            from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer

            # Attaches to the active provider (creating one only if none
            # exists), so the memoized proxy tracers keep resolving correctly.
            tracer = OpentelemetryTracer(exporters=[])
            spans_before = len(tracer._inmemory_exporter._exporter._spans)
            kwargs.setdefault("tracers", [tracer])

        if arm == "codex":
            self._install_codex_doubles(backend)

        # The ADK arm consumes the plan through a BaseLlm; the Codex arm
        # resolves the model from model_name and reaches the plan through the
        # shim. Passing Agent(model=...) under codex is a hard error in
        # veadk.runtime.compat, so the two arms differ only here.
        if arm == "adk":
            kwargs["model"] = backend.as_base_llm()
        agent = Agent(
            name=agent_name,
            description="A differential parity agent.",
            instruction="Answer the user.",
            model_name="scripted-model",
            model_api_base="https://backend.invalid/v1",
            model_api_key="backend-key",
            runtime=arm,
            **kwargs,
        )

        session_service = InMemorySessionService()
        await session_service.create_session(
            app_name="parity", user_id="user", session_id=session_id
        )
        runner = Runner(app_name="parity", agent=agent, session_service=session_service)

        outcome = RunOutcome(arm=arm, calls=backend.calls)
        events: list[Any] = []
        try:
            async for event in runner.run_async(
                user_id="user",
                session_id=session_id,
                new_message=types.Content(
                    role="user", parts=[types.Part(text=user_text)]
                ),
                **({"run_config": run_config} if run_config is not None else {}),
            ):
                events.append(event)
        except BaseException as e:  # noqa: BLE001 - the error IS an observable
            outcome.error = e

        session = await session_service.get_session(
            app_name="parity", user_id="user", session_id=session_id
        )
        outcome.events = events
        outcome.authors = tuple(getattr(e, "author", "") for e in events)
        normalized = normalize_events(events, agent_name)
        outcome.final_text = normalized["final_text"]
        outcome.tool_calls = normalized["tool_calls"]
        outcome.tool_responses = normalized["tool_responses"]
        outcome.state_delta = normalized["state_delta"]
        outcome.event_kinds = normalized["kinds"]
        outcome.usage = normalized["usage"]
        outcome.session_state = dict(getattr(session, "state", None) or {})
        outcome.declared_usage = backend.declared_usage_total
        if tracer is not None:
            spans = tracer._inmemory_exporter._exporter._spans[spans_before:]
            outcome.span_names = frozenset(span.name for span in spans)

        if arm == "codex" and codex_fault is not None:
            codex_fault(outcome)
        return outcome

    def _install_codex_doubles(self, backend: ScriptedBackend) -> None:
        """Wire the Codex arm to the in-process shim with no socket or binary."""
        fake_codex_sdk.install_openai_codex_stub()

        from veadk.runtime.codex import runtime as runtime_module
        from veadk.runtime.codex.proxy import ResponsesShim

        shim = ResponsesShim("https://backend.invalid/v1", "backend-key")
        shim.url = f"http://shim-{uuid.uuid4().hex[:12]}"
        fake_codex_sdk.SHIM_REGISTRY[shim.url] = shim
        self.monkeypatch.setattr(
            "veadk.runtime.codex.proxy.litellm.aresponses", backend.as_aresponses()
        )

        async def fake_get_shim(api_base: str, api_key: str) -> Any:
            return shim

        self.monkeypatch.setattr(runtime_module, "get_shim", fake_get_shim)
        self.monkeypatch.setattr(
            runtime_module, "AsyncCodex", fake_codex_sdk.ShimDrivingCodex
        )
        self.shim = shim


@pytest.fixture
def parity_runner(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Function-scoped runner: no shared state can leak between rows."""
    fake_codex_sdk.REQUEST_LOG.clear()
    # The compat layer dedupes warnings per (agent id, field) process-wide, so
    # a row asserting on a warning must start from a clean slate.
    from veadk.runtime.compat import reset_warning_state

    reset_warning_state()
    runner = ParityRunner(monkeypatch)
    yield runner
    reset_warning_state()
    fake_codex_sdk.SHIM_REGISTRY.clear()
    fake_codex_sdk.REQUEST_LOG.clear()
    from veadk.runtime import get_runtime

    get_runtime.cache_clear()


@pytest.fixture
def compare() -> Any:
    """Expose :func:`compare_runs` so tests never import conftest directly."""
    return compare_runs


@pytest.fixture
def event_classifier() -> Any:
    return classify_event


# NOTE: this suite deliberately does *not* swap OpenTelemetry's process-global
# ``TracerProvider`` per test. ADK's and VeADK's module-level tracers are
# ``ProxyTracer`` objects that memoize the first real provider they resolve, so
# installing a second provider mid-session silently sends every later span into
# a detached (often already shut down) pipeline -- which looks exactly like "the
# runtime emits no spans". Each ``capture_spans`` row instead attaches its own
# ``InMemoryExporter`` to whichever provider is already active and reads back
# only the spans produced during its own run.


__all__ = [
    "COMPARED_KINDS",
    "EXCLUDED_KINDS",
    "ParityRunner",
    "RecordedCall",
    "Round",
    "RunOutcome",
    "ScriptedBackend",
    "classify_event",
    "compare_runs",
    "fake_codex_sdk",
    "normalize_events",
    "scripted_backend",
]
