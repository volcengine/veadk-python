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

"""ADK-compatible output_key handling for pluggable runtimes."""

from __future__ import annotations

from typing import Any, Optional

from google.adk.events.event import Event
from google.adk.utils._schema_utils import validate_schema

from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def maybe_save_output_to_state(agent: Any, event: Event) -> None:
    """Save a final model text response to ``event.actions.state_delta``.

    This mirrors ADK's ``LlmAgent.__maybe_save_output_to_state`` for runtimes
    that bypass ADK's built-in LLM flow, with two behaviours that ADK does not
    need but external harnesses do.

    **Last write wins.** ``Event.is_final_response()`` is True for *every*
    non-partial, tool-free text event, so a harness that streams several
    complete assistant messages in one turn (Codex ``agentMessage`` items) makes
    this run once per message. Each run overwrites ``state_delta[output_key]``,
    so the value that survives the turn is the agent's *last* message — never a
    concatenation of its intermediate thinking. That is the ADK meaning of
    ``output_key`` ("the agent's answer") and it is what makes ``output_schema``
    validation meaningful. It is also stable if a runtime later marks
    intermediate items ``partial=True``: those stop being final responses, only
    the real final message reaches this function, and the outcome is unchanged.

    **The ``output_schema`` branch is unreachable by construction.**
    ``veadk.runtime.compat`` classifies ``output_schema`` as ``"error"`` for
    every non-``adk`` runtime, and that gate runs a few lines above this
    function's only call site in :meth:`veadk.agent.Agent._run_async_impl`. The
    rule is right: the schema reaches neither the backend nor the prompt (it is
    written to ``LlmRequest.config.response_schema``, which the prompt builder
    never reads), so the model is not constrained and "structured output" would
    not be structured.

    The branch is nonetheless *guarded rather than raising*, so that demoting
    the rule can never kill a turn mid-stream: ``validate_schema`` calls
    ``model_validate_json``, which raises on prose, and this runs on every
    event of the invocation. A non-conforming final text is skipped with a
    warning; any value an earlier event wrote stays in place. The real
    protection against an accidental demotion is the test asserting that rule
    stays at ``"error"`` — see ``tests/runtime/differential/``.

    Args:
        agent (Any): The agent that produced the event. Read defensively.
        event (google.adk.events.event.Event): The event to inspect. Mutated in
            place when a value is saved.
    """
    if event.author != agent.name:
        return

    output_key: Optional[str] = getattr(agent, "output_key", None)
    if not output_key:
        return

    if not event.is_final_response():
        return

    if not event.content or not event.content.parts:
        return

    has_text_part = any(
        part.text is not None and not getattr(part, "thought", False)
        for part in event.content.parts
    )
    if not has_text_part:
        return

    result: Any = "".join(
        part.text
        for part in event.content.parts
        if part.text and not getattr(part, "thought", False)
    )

    output_schema = getattr(agent, "output_schema", None)
    if output_schema:
        # Unreachable while compat keeps output_schema at "error" — see the
        # docstring. Guarded anyway so a demotion cannot kill a turn mid-stream.
        if not result.strip():
            return
        try:
            result = validate_schema(output_schema, result)
        except Exception:  # noqa: BLE001 - pydantic/json errors must not kill a run
            logger.warning(
                "Agent '%s' final response does not match output_schema %s; "
                "skipping the state['%s'] write. Drop output_schema, or use "
                "runtime='adk'.",
                getattr(agent, "name", "<unknown>"),
                getattr(output_schema, "__name__", type(output_schema).__name__),
                output_key,
            )
            return

    event.actions.state_delta[output_key] = result
