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

"""A tiny, fixed real-model canary for ``Agent(runtime="codex")``.

Every other Codex test stubs the model. The regressions that actually shipped
only showed up against a real model, and the only way to see them used to be
running a large example (``examples/codex_ops_assistant`` spends ~2M tokens a
run). This probe is the bounded replacement: one fixed two-turn scenario,
~75K tokens in total, meant to be run **once per Codex PR before merge**.

Scenario (the same one used for manual verification of the replay-order fix):

* turn 1: call the ADK function tool ``fetch_latency_samples`` (returns a
  six-row CSV), then three shell steps -- save the CSV, compute the average
  p99 (322.83), compute the max p99 (980) -- and report both;
* turn 2: from the same file, compute the min p99 (120).

What it catches, each mapped to a regression we have hit:

1. Ark rejecting a request field the shim forwarded (``reasoning.summary``):
   the turn errors out instead of completing.
2. Replayed tool history out of order (ADK tool results appended at the tail):
   the model loops and runs into ``max_llm_calls`` (15) ->
   ``LlmCallsLimitExceededError``, or repeats the same command.
3. The model copying Codex's shell wrapper into its own commands
   (``/bin/zsh -lc '/bin/zsh -lc ...'``): a recorded command still starts with
   a wrapper after the runtime's one-level unwrap.
4. An ADK tool executed more than once: the fetch counter is not 1.
5. Multi-turn context lost: turn 2 cannot find/compute the min.

Plus a cost guard: the summed token usage of the run must stay under
``CODEX_PROBE_MAX_TOKENS`` (default 150000), so a cost regression (e.g. a
bloated prompt or an extra replay) fails loudly too.

This spends real tokens, so it never runs by default -- and never in CI. Opt in
with::

    CODEX_RUN_PROBE=1 MODEL_AGENT_API_KEY=... MODEL_AGENT_API_BASE=... \\
    MODEL_AGENT_NAME=... pytest tests/runtime/codex/test_codex_real_model_probe.py \\
        -p no:xdist -s -rs
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field

import pytest

_REQUIRED_MODEL_ENV = (
    "MODEL_AGENT_API_KEY",
    "MODEL_AGENT_API_BASE",
    "MODEL_AGENT_NAME",
)
_DEFAULT_MAX_TOKENS = 150_000
#: Per-turn wall clock bound. A healthy turn takes well under a minute; this is
#: generous for a slow backend but still stops a hung Codex subprocess.
_TURN_TIMEOUT_SECONDS = 240.0
_MAX_LLM_CALLS = 15

_CSV = "minute,p99_ms\n1,120\n2,135\n3,410\n4,980\n5,150\n6,142"

#: A command that still starts with a shell wrapper after the runtime's own
#: one-level unwrap, i.e. the model wrapped it itself.
_SHELL_WRAPPER = re.compile(r"^\s*\S*/(?:sh|bash|zsh)\s+-l?c\s")

_TURN_1 = (
    "Fetch the latency samples for checkout-api with the tool. Then, one shell "
    "command per step: (1) save the CSV to latency.csv, (2) compute the average "
    "p99 with python3, (3) compute the max p99 with python3. Finally report the "
    "average (2 decimals) and the max."
)
_TURN_2 = "Using latency.csv, compute the minimum p99 with python3 and report it."


def _skip_reason() -> str | None:
    if os.environ.get("CODEX_RUN_PROBE") != "1":
        return (
            "real-model Codex probe spends tokens; set CODEX_RUN_PROBE=1 plus "
            "MODEL_AGENT_API_KEY, MODEL_AGENT_API_BASE and MODEL_AGENT_NAME to run it"
        )
    missing = [name for name in _REQUIRED_MODEL_ENV if not os.environ.get(name)]
    if missing:
        return (
            f"CODEX_RUN_PROBE=1 but {', '.join(missing)} not set; set "
            "MODEL_AGENT_API_KEY, MODEL_AGENT_API_BASE and MODEL_AGENT_NAME"
        )
    if importlib.util.find_spec("openai_codex") is None:
        return (
            "openai-codex SDK is not installed; run `uv sync --all-extras` "
            "(or pip install openai-codex)"
        )
    return None


_SKIP_REASON = _skip_reason()

pytestmark = [
    pytest.mark.codex_probe,
    pytest.mark.skipif(_SKIP_REASON is not None, reason=_SKIP_REASON or ""),
]


def _max_tokens() -> int:
    raw = os.environ.get("CODEX_PROBE_MAX_TOKENS")
    return int(raw) if raw else _DEFAULT_MAX_TOKENS


@dataclass
class _TurnResult:
    commands: list[str] = field(default_factory=list)
    adk_calls: list[str] = field(default_factory=list)
    final_text: str = ""
    #: Summed ``usage_metadata.total_token_count`` of durable events. The
    #: runtime attaches the Codex thread's cumulative total exactly once per
    #: invocation (the shim folds ADK-tool rounds into it), so this is the turn.
    usage_tokens: int = 0
    #: Fallback: highest cumulative ``total`` seen on the ``token_usage``
    #: lifecycle events, in case the final bookkeeping event is missing.
    lifecycle_tokens: int = 0
    budget_exceeded: bool = False
    seconds: float = 0.0

    @property
    def tokens(self) -> int:
        return self.usage_tokens or self.lifecycle_tokens


def _lifecycle_total(event) -> int:
    meta = event.custom_metadata or {}
    if meta.get("codex_event_type") != "token_usage":
        return 0
    usage = meta.get("token_usage") or {}
    total = usage.get("total") or usage.get("last") or {}
    if not isinstance(total, dict):
        return 0
    value = total.get("total_tokens", total.get("totalTokens"))
    if isinstance(value, int):
        return value
    return int(total.get("input_tokens") or 0) + int(total.get("output_tokens") or 0)


async def _run_turn(runner, session_id: str, text: str) -> _TurnResult:
    from google.adk.agents import RunConfig
    from google.adk.agents.invocation_context import LlmCallsLimitExceededError
    from google.genai import types

    result = _TurnResult()
    seen_call_ids: set[str] = set()
    started = time.monotonic()

    async def _consume() -> None:
        async for event in runner.run_async(
            user_id=runner.user_id,
            session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=text)]),
            run_config=RunConfig(max_llm_calls=_MAX_LLM_CALLS),
        ):
            result.lifecycle_tokens = max(
                result.lifecycle_tokens, _lifecycle_total(event)
            )
            for call in event.get_function_calls() or []:
                # A call is announced on item start and must not be counted
                # again if a completed item repeats it.
                if call.id:
                    if call.id in seen_call_ids:
                        continue
                    seen_call_ids.add(call.id)
                if call.name == "exec_command":
                    result.commands.append(str((call.args or {}).get("command", "")))
                else:
                    result.adk_calls.append(call.name)
            if event.partial:
                continue
            if event.usage_metadata and event.usage_metadata.total_token_count:
                result.usage_tokens += event.usage_metadata.total_token_count
            if event.content:
                for part in event.content.parts or []:
                    if part.text and not part.thought:
                        result.final_text = part.text

    try:
        await asyncio.wait_for(_consume(), timeout=_TURN_TIMEOUT_SECONDS)
    except LlmCallsLimitExceededError:
        result.budget_exceeded = True
    result.seconds = time.monotonic() - started
    return result


def _describe(label: str, turn: _TurnResult) -> str:
    cmds = "\n".join(f"    - {c[:160]!r}" for c in turn.commands)
    return (
        f"{label}: {turn.seconds:.1f}s tokens={turn.tokens} "
        f"budget_exceeded={turn.budget_exceeded} adk_calls={turn.adk_calls}\n"
        f"  commands ({len(turn.commands)}):\n{cmds}\n"
        f"  final: {turn.final_text!r}"
    )


def _has_number(text: str, *candidates: str) -> bool:
    return any(
        re.search(rf"(?<![\d.]){re.escape(c)}(?![\d])", text) for c in candidates
    )


@pytest.mark.asyncio
async def test_codex_real_model_two_turn_probe():
    from veadk import Agent, Runner
    from veadk.memory.short_term_memory import ShortTermMemory

    fetches: list[str] = []

    def fetch_latency_samples(service: str) -> dict:
        """Fetch recent p99 latency samples (ms) for a service."""
        fetches.append(service)
        return {"service": service, "csv": _CSV}

    agent = Agent(
        name="latency_probe",
        description="latency analyst",
        instruction="Be concise.",
        runtime="codex",
        model_name=os.environ["MODEL_AGENT_NAME"],
        model_api_base=os.environ["MODEL_AGENT_API_BASE"],
        model_api_key=os.environ["MODEL_AGENT_API_KEY"],
        tools=[fetch_latency_samples],
    )
    runner = Runner(agent=agent, short_term_memory=ShortTermMemory())
    session_id = f"codex-probe-{uuid.uuid4().hex[:8]}"
    await runner.short_term_memory.create_session(
        app_name=runner.app_name, user_id=runner.user_id, session_id=session_id
    )

    turn1 = await _run_turn(runner, session_id, _TURN_1)
    turn2 = await _run_turn(runner, session_id, _TURN_2)
    report = (
        _describe("turn 1", turn1)
        + "\n"
        + _describe("turn 2", turn2)
        + f"\nfetch executions: {fetches}"
    )
    print("\n" + report)

    # (2) no looping into the LLM-call budget, on either turn.
    assert not turn1.budget_exceeded, report
    assert not turn2.budget_exceeded, report

    # (4) the ADK tool ran exactly once, and only in turn 1.
    assert fetches == ["checkout-api"], report

    # (2) the three shell steps happened, without the same command repeated.
    assert len(turn1.commands) >= 3, report
    repeated = {c: n for c, n in Counter(turn1.commands).items() if n > 2}
    assert not repeated, f"commands repeated more than twice: {repeated}\n{report}"

    # (3) the model never re-wrapped a command in a shell itself.
    wrapped = [c for c in turn1.commands + turn2.commands if _SHELL_WRAPPER.match(c)]
    assert not wrapped, f"self-wrapped shell commands: {wrapped}\n{report}"

    # (1)/(5) both turns answered, with the right numbers.
    assert _has_number(turn1.final_text, "322.83", "322.8"), report
    assert _has_number(turn1.final_text, "980"), report
    assert _has_number(turn2.final_text, "120"), report

    # Cost guard.
    total_tokens = turn1.tokens + turn2.tokens
    assert total_tokens > 0, f"no token usage was reported\n{report}"
    cap = _max_tokens()
    assert total_tokens <= cap, (
        f"probe used {total_tokens} tokens, over CODEX_PROBE_MAX_TOKENS={cap}\n{report}"
    )
