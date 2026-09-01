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

"""Support matrix for non-``adk`` agent runtimes.

``Agent(runtime="codex")`` and ``Agent(runtime="piagent")`` replace the *entire*
ADK LLM flow with an external harness. Everything ADK implements inside that
flow — agent transfer, request/response processors, the ``LlmRequest``
assembly, per-call callbacks — therefore does not run. Without a check, a large
part of :class:`veadk.agent.Agent`'s configuration surface is accepted at
construction time and then silently ignored at run time.

This module is the single, runtime-agnostic place that states which
configuration is unsupported and how loudly to say so:

* ``"error"`` — the configuration produces a *wrong answer* (not just a missing
  feature), so the agent must not run at all. Raised as :class:`ValueError`.
* ``"warn"`` — the configuration is dropped but the turn still produces a
  reasonable answer. Logged once per ``(agent identity, field)`` so a
  per-request cloned agent does not spam the log.

Rules read agent state defensively, so a duck-typed stand-in that happens not to
carry a field simply fires no rule. That keeps the checker usable from
:meth:`veadk.agent.Agent._run_async_impl` without constraining what the runtime
tests may pass directly into ``Runtime.run_async``.

Deliberately *not* covered: ``context_cache_config`` and ``parallel_worker``.
Neither is read by veadk or google-adk 2.2.0 on the ``adk`` path either, so
blaming the runtime for ignoring them would be wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from typing import Any, Callable, Literal, Optional

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

Policy = Literal["error", "warn"]
"""How loudly an unsupported configuration is reported."""

ALL_RUNTIMES: frozenset[str] = frozenset({"codex", "piagent"})
"""Every runtime that bypasses ADK's LLM flow."""

EXPLICIT_FIELDS_ATTR = "_veadk_explicit_fields"
"""Private attribute holding the caller-set field names.

:class:`veadk.agent.Agent` snapshots ``model_fields_set`` into this attribute at
the *top* of ``model_post_init``. The raw ``model_fields_set`` cannot be used:
``Agent.model_post_init`` assigns ``model``/``model_extra_config``/
``run_processor`` itself, and ``BaseAgent.clone()`` re-assigns every list field,
so by the time anything can be checked those names are always "set".
"""


def explicit_fields(agent: Any) -> frozenset[str]:
    """Return the field names the *caller* passed to the agent constructor.

    Args:
        agent (Any): The agent (or duck-typed stand-in) to inspect.

    Returns:
        frozenset[str]: Caller-set field names. Falls back to
        ``agent.model_fields_set`` when no snapshot is available, and to an
        empty set for objects that are not pydantic models.
    """
    snapshot = getattr(agent, EXPLICIT_FIELDS_ATTR, None)
    if isinstance(snapshot, (frozenset, set)):
        return frozenset(snapshot)
    return frozenset(getattr(agent, "model_fields_set", frozenset()) or ())


@dataclass(frozen=True)
class SupportRule:
    """One unsupported-configuration rule.

    Attributes:
        field (str): The ``Agent`` field the rule is about. Also the dedup key
            for ``warn`` rules.
        policy (Policy): ``"error"`` or ``"warn"``.
        predicate (Callable[[Any, frozenset[str]], bool]): Receives the agent
            and its :func:`explicit_fields`; returns whether the rule fires.
        message (Callable[[Any, str], str]): Receives the agent and the runtime
            name; returns the user-facing message.
        applies_to (frozenset[str]): Runtimes the rule applies to.
    """

    field: str
    policy: Policy
    predicate: Callable[[Any, frozenset[str]], bool]
    message: Callable[[Any, str], str]
    applies_to: frozenset[str] = dataclass_field(default=ALL_RUNTIMES)


def _truthy(name: str) -> Callable[[Any, frozenset[str]], bool]:
    """Build a predicate that fires when ``agent.<name>`` is truthy."""

    def _predicate(agent: Any, _explicit: frozenset[str]) -> bool:
        return bool(getattr(agent, name, None))

    return _predicate


def _explicitly_set(name: str) -> Callable[[Any, frozenset[str]], bool]:
    """Build a predicate that fires when the caller passed ``name``."""

    def _predicate(_agent: Any, explicit: frozenset[str]) -> bool:
        return name in explicit

    return _predicate


def _dropped_generate_content_fields(agent: Any) -> list[str]:
    """Return ``generate_content_config`` fields no external runtime forwards.

    Only ``system_instruction`` survives the bridge into an external harness;
    everything else (``temperature``, ``max_output_tokens``, ``thinking_config``,
    ...) is assembled by ADK's flow and never reaches the backend here.
    """
    config = getattr(agent, "generate_content_config", None)
    if config is None:
        return []
    fields = getattr(config, "model_fields_set", None)
    if not fields:
        return []
    return sorted(set(fields) - {"system_instruction"})


def _model_name_fallbacks(agent: Any) -> list[str]:
    """Return the ``model_name`` entries after the first one."""
    model_name = getattr(agent, "model_name", None)
    if isinstance(model_name, list) and len(model_name) > 1:
        return [str(name) for name in model_name[1:]]
    return []


SUPPORT_RULES: tuple[SupportRule, ...] = (
    # --- error: silently wrong results -------------------------------------
    SupportRule(
        field="sub_agents",
        policy="error",
        predicate=_truthy("sub_agents"),
        message=lambda agent, rt: (
            f"{rt} runtime does not implement agent transfer, so "
            "Agent(sub_agents=...) is unreachable and the agent will silently "
            "answer every request itself. Use runtime='adk', or drive "
            "delegation from a parent SequentialAgent/AgentTool."
        ),
    ),
    SupportRule(
        field="model",
        policy="error",
        predicate=_explicitly_set("model"),
        message=lambda _agent, rt: (
            f"{rt} runtime resolves the model from Agent(model_name=...) and "
            "ignores the Agent(model=...) object entirely, so its api_base, "
            "headers and fallbacks are dropped. Set model_name instead, or use "
            "runtime='adk'."
        ),
    ),
    SupportRule(
        field="generate_content_config",
        policy="error",
        predicate=lambda agent, _explicit: bool(
            _dropped_generate_content_fields(agent)
        ),
        message=lambda agent, rt: (
            f"{rt} runtime forwards only "
            "generate_content_config.system_instruction; "
            f"{', '.join(_dropped_generate_content_fields(agent))} would be "
            "silently dropped. Remove them, or use runtime='adk'."
        ),
    ),
    SupportRule(
        field="output_schema",
        policy="error",
        predicate=_truthy("output_schema"),
        message=lambda _agent, rt: (
            f"{rt} runtime never sends Agent(output_schema=...) to the backend, "
            "so the model is not constrained and validation of its prose reply "
            "will fail at the end of the turn. Use runtime='adk', or drop "
            "output_schema and parse the reply yourself."
        ),
    ),
    SupportRule(
        field="planner",
        policy="error",
        predicate=_truthy("planner"),
        message=lambda _agent, rt: (
            "Agent(planner=...) runs as an ADK request/response processor, "
            f"which {rt} runtime never executes, so it has no effect on the "
            "turn. Use runtime='adk', or remove planner."
        ),
    ),
    SupportRule(
        field="code_executor",
        policy="error",
        predicate=_truthy("code_executor"),
        message=lambda _agent, rt: (
            "Agent(code_executor=...) runs as an ADK request/response "
            f"processor, which {rt} runtime never executes, so it has no effect "
            "on the turn. Use runtime='adk', or remove code_executor."
        ),
    ),
    SupportRule(
        field="include_contents",
        policy="error",
        predicate=lambda agent, _explicit: (
            getattr(agent, "include_contents", None) == "none"
        ),
        message=lambda _agent, rt: (
            f"{rt} runtime always sends the full conversation history; "
            "include_contents='none' would be silently ignored and prior turns "
            "leaked to the model. Use runtime='adk', or leave include_contents "
            "at 'default'."
        ),
    ),
    SupportRule(
        field="enable_supervisor",
        policy="error",
        predicate=_truthy("enable_supervisor"),
        message=lambda _agent, rt: (
            "Agent(enable_supervisor=True) is installed through the ADK LLM "
            f"flow, which {rt} runtime replaces, so no supervision runs. Use "
            "runtime='adk', or set enable_supervisor=False."
        ),
    ),
    # --- warn: dropped, but the turn still answers --------------------------
    SupportRule(
        field="model_name",
        policy="warn",
        predicate=lambda agent, _explicit: bool(_model_name_fallbacks(agent)),
        message=lambda agent, rt: (
            f"{rt} runtime uses only the first entry of Agent(model_name=[...]) "
            f"and drops the fallbacks {_model_name_fallbacks(agent)}, because "
            "the fallback chain lives on the LiteLLM client this runtime never "
            "builds; a backend failure will surface as an error instead of "
            "failing over. Pass a single model name, or use runtime='adk' if "
            "you need fallbacks."
        ),
    ),
    SupportRule(
        field="model_provider",
        policy="warn",
        predicate=lambda agent, _explicit: bool(getattr(agent, "model_provider", None))
        and getattr(agent, "model_provider", None) != "openai",
        message=lambda agent, rt: (
            f"{rt} runtime always talks to model_api_base over an "
            "OpenAI-compatible API and ignores "
            f"Agent(model_provider={getattr(agent, 'model_provider', None)!r}), "
            "because the provider prefix only selects a LiteLLM client that is "
            "never created here; a non-OpenAI-compatible endpoint will fail at "
            "call time. Use runtime='adk' if the provider matters."
        ),
    ),
    SupportRule(
        field="model_extra_config",
        policy="warn",
        predicate=_explicitly_set("model_extra_config"),
        message=lambda _agent, rt: (
            f"{rt} runtime drops Agent(model_extra_config=...) — both "
            "extra_headers and extra_body, including the VeADK Ark defaults for "
            "request encryption and prompt caching — because it does not build "
            "the LiteLLM/Ark client those options configure, so requests go out "
            "unencrypted and uncached. Use runtime='adk' if you need them."
        ),
        # codex forwards it: the runtime hands it to `register_turn` and the
        # shim applies extra_headers/extra_body to every backend call.
        applies_to=frozenset({"piagent"}),
    ),
    SupportRule(
        field="enable_responses",
        policy="warn",
        predicate=_truthy("enable_responses"),
        message=lambda _agent, rt: (
            f"{rt} runtime drives the backend itself and ignores "
            "Agent(enable_responses=True) together with enable_responses_cache, "
            "because the Ark Responses client (and its previous_response_id "
            "continuation and response caching) is part of the ADK model layer "
            "this runtime replaces. Use runtime='adk' to get the Responses API."
        ),
    ),
    SupportRule(
        field="example_store",
        policy="warn",
        predicate=_truthy("example_store"),
        message=lambda _agent, rt: (
            "Agent(example_store=...) is delivered by "
            f"ExampleTool.process_llm_request, which {rt} runtime never calls, "
            "so no few-shot examples reach the model. Use runtime='adk', or "
            "put the examples in the instruction."
        ),
    ),
    SupportRule(
        field="knowledgebase",
        policy="warn",
        predicate=_truthy("knowledgebase"),
        message=lambda _agent, rt: (
            "Agent(knowledgebase=...) is silently disabled under "
            f"{rt} runtime: the VeADK knowledge base is wired in by "
            "LoadKnowledgebaseTool.process_llm_request, the ADK hook that tells "
            f"the model the knowledge base exists and when to query it, and {rt} "
            "runtime never calls it, so retrieval is not triggered and answers "
            "fall back to the model's own knowledge. Use runtime='adk', or "
            "perform the retrieval yourself and pass the result in the "
            "instruction."
        ),
    ),
    SupportRule(
        field="skills_mode",
        policy="warn",
        predicate=_truthy("skills_mode"),
        message=lambda agent, rt: (
            "Agent(skills_mode="
            f"{getattr(agent, 'skills_mode', None)!r}) has no effect: {rt} "
            "runtime skips VeADK's SkillsToolset when bridging tools, so the "
            "instruction advertises execute_skills/skills_tool while no such "
            "tool is registered and every call fails. Use runtime='adk', or "
            "pass the skills through a runtime-native skill toolset instead."
        ),
    ),
    SupportRule(
        field="enable_skills_checklist",
        policy="warn",
        predicate=_truthy("enable_skills_checklist"),
        message=lambda _agent, rt: (
            "Agent(enable_skills_checklist=True) installs an ADK before-tool "
            f"callback over VeADK skills, and {rt} runtime bridges neither the "
            "skills toolset nor per-tool ADK callbacks, so no checklist is ever "
            "enforced. Use runtime='adk', or set enable_skills_checklist=False."
        ),
    ),
    SupportRule(
        field="after_model_callback",
        policy="warn",
        predicate=_truthy("after_model_callback"),
        message=lambda _agent, rt: (
            f"Agent(after_model_callback=...) behaves differently under {rt} "
            "runtime: it fires once per turn on the merged final text, not once "
            "per LLM call, because the inner model loop runs inside the "
            "external harness, so intermediate model responses cannot be "
            "inspected or rewritten. Use runtime='adk' if you need per-call "
            "callbacks."
        ),
    ),
    SupportRule(
        field="tracers",
        policy="warn",
        predicate=_truthy("tracers"),
        # Deliberately does not claim a per-turn span exists: whether one is
        # emitted is per-runtime, but "no span per model call" holds for both.
        message=lambda _agent, rt: (
            f"Agent(tracers=...) records no per-model-call spans under {rt} "
            "runtime: the harness's own loop issues several backend calls per "
            "turn and is not instrumented by ADK, so their individual prompts, "
            "responses and token splits are not broken out. Use runtime='adk' "
            "for per-call tracing."
        ),
    ),
    SupportRule(
        field="codex_runtime_config",
        policy="warn",
        predicate=_truthy("codex_runtime_config"),
        applies_to=frozenset({"piagent"}),
        message=lambda agent, rt: (
            "Agent(codex_runtime_config=...) configures the codex runtime only; "
            f"{rt} runtime ignores it, so its sandbox, approval_mode, "
            "network_access and workspace settings do not apply to this agent. "
            "Remove it, or set runtime='codex'."
        ),
    ),
)


_RUN_CONFIG_FIELD = "run_config.max_llm_calls"


def _run_config_message(runtime: str) -> str:
    # ADK's only enforcement point is
    # ``InvocationContext.increment_llm_call_count()``, reached from
    # ``base_llm_flow``, which no external runtime executes. codex charges the
    # budget itself before each backend call, so it never reaches this message
    # (see the guard in ``check_agent_runtime_support``). piagent can only
    # charge a call the Pi binary has already finished, hence the overshoot.
    return (
        f"RunConfig(max_llm_calls=...) is enforced one call late under "
        f"{runtime} runtime: the model loop runs inside the external harness, "
        "which reports a call only once it has completed, so the invocation "
        "aborts just past the limit rather than just short of it. Use "
        "runtime='adk' for exact enforcement."
    )


_WARNED: set[tuple[str, str]] = set()
"""``(agent identity, field)`` pairs already warned about in this process."""


def _agent_identity(agent: Any) -> str:
    """Return a stable identity for warning deduplication.

    ``Agent.id`` is preferred so that per-request clones (which copy ``id``)
    share one warning instead of logging on every request.
    """
    identity = getattr(agent, "id", None)
    if isinstance(identity, str) and identity:
        return identity
    return f"{type(agent).__name__}:{id(agent):x}"


def _warn_once(agent: Any, field: str, message: str) -> None:
    key = (_agent_identity(agent), field)
    if key in _WARNED:
        return
    _WARNED.add(key)
    logger.warning(message)


def reset_warning_state() -> None:
    """Clear the once-per-``(agent, field)`` warning cache. For tests."""
    _WARNED.clear()


def check_agent_runtime_support(
    agent: Any,
    runtime: str,
    *,
    run_config: Optional[Any] = None,
) -> None:
    """Validate an agent against a runtime's support matrix.

    Args:
        agent (Any): The agent about to run. Read defensively, so a duck-typed
            stand-in without the inspected fields fires no rule.
        runtime (str): Runtime name from ``Agent(runtime=...)``. ``"adk"`` (and
            any falsy value) returns immediately.
        run_config (Optional[Any]): The invocation's ``RunConfig``, when the
            check runs at invocation time. Fields that only exist per
            invocation are checked only when this is provided.

    Raises:
        ValueError: On the first ``error``-policy violation, in the declaration
            order of :data:`SUPPORT_RULES`. ``warn``-policy violations are
            logged once per ``(agent identity, field)`` and never raise.
    """
    if not runtime or runtime == "adk":
        return

    explicit = explicit_fields(agent)
    for rule in SUPPORT_RULES:
        if runtime not in rule.applies_to:
            continue
        try:
            triggered = rule.predicate(agent, explicit)
        except Exception:  # noqa: BLE001 - a probe must never break a run
            continue
        if not triggered:
            continue
        if rule.policy == "error":
            raise ValueError(rule.message(agent, runtime))
        _warn_once(agent, rule.field, rule.message(agent, runtime))

    # codex charges every backend model call through
    # `ResponsesShim.register_turn(on_model_call=...)`, *before* the call, so
    # the budget binds exactly and warning would be a false positive. piagent
    # charges each call the Pi binary reports as finished, which still enforces
    # the budget but only after the overrunning call has run.
    if run_config is not None and runtime != "codex":
        fields = getattr(run_config, "model_fields_set", None) or ()
        if "max_llm_calls" in fields:
            _warn_once(agent, _RUN_CONFIG_FIELD, _run_config_message(runtime))


__all__ = [
    "ALL_RUNTIMES",
    "EXPLICIT_FIELDS_ATTR",
    "Policy",
    "SUPPORT_RULES",
    "SupportRule",
    "check_agent_runtime_support",
    "explicit_fields",
    "reset_warning_state",
]
