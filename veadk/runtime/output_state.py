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

import re
from typing import Any, Optional

from google.adk.events.event import Event
from google.adk.utils._schema_utils import validate_schema

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

_FENCED_BLOCK = re.compile(
    r"```[ \t]*(?:json|JSON)?[ \t]*\r?\n(?P<body>.*?)\r?\n?[ \t]*```",
    re.DOTALL,
)


def _validated_or_none(output_schema: Any, text: str) -> tuple[bool, Any]:
    """Validate ``text`` against ``output_schema`` without ever raising.

    Returns:
        tuple[bool, Any]: ``(True, value)`` when ``text`` validates, otherwise
        ``(False, None)``.
    """
    try:
        return True, validate_schema(output_schema, text)
    except Exception:  # noqa: BLE001 - pydantic/json errors must not kill a run
        return False, None


def _coerce_to_schema(output_schema: Any, text: str) -> tuple[bool, Any]:
    """Try to read a schema-conforming value out of a model's reply.

    Two shapes are accepted, in order:

    1. The whole reply (stripped) is the JSON payload.
    2. The reply contains exactly one fenced code block (```` ```json ... ``` ````
       or a bare ```` ``` ... ``` ````) whose body is the JSON payload. A fence is
       an unambiguous delimiter, so any prose around it can be discarded safely.

    Anything else — prose with a bare ``{...}`` somewhere inside it, several
    fenced blocks, truncated JSON — is *rejected rather than salvaged*. Locating
    "the JSON" inside free-form prose is guesswork: braces occur in prose, a
    reply may contain several candidate objects, and a wrong guess silently
    writes a mangled value into tenant session state. Skipping leaves the
    previous value in place, which is recoverable; a wrong write is not.

    Returns:
        tuple[bool, Any]: ``(True, value)`` on success, ``(False, None)``
        otherwise.
    """
    ok, value = _validated_or_none(output_schema, text.strip())
    if ok:
        return True, value

    blocks = _FENCED_BLOCK.findall(text)
    if len(blocks) == 1:
        return _validated_or_none(output_schema, blocks[0].strip())

    return False, None


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

    **Never raises.** ``validate_schema`` calls ``model_validate_json``, which
    raises ``pydantic.ValidationError`` on prose. External harnesses emit prose
    constantly, and this runs on every event of the invocation, so a raise here
    would kill the whole turn. An unparseable or non-conforming final text is
    therefore *skipped with a warning*: nothing is written, and any value an
    earlier event wrote stays in place. Skipping matches ADK's "do not write
    garbage" contract and cannot take down a tenant's run.

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
        if not result.strip():
            return
        ok, validated = _coerce_to_schema(output_schema, result)
        if not ok:
            logger.warning(
                "Agent '%s' final response does not match output_schema %s; "
                "skipping the state['%s'] write. External runtimes do not "
                "constrain the model to the schema, so free-form replies are "
                "expected. Drop output_schema, or use runtime='adk'.",
                getattr(agent, "name", "<unknown>"),
                getattr(output_schema, "__name__", type(output_schema).__name__),
                output_key,
            )
            return
        result = validated

    event.actions.state_delta[output_key] = result
