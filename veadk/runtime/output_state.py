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

from typing import Any

from google.adk.events.event import Event
from google.adk.utils._schema_utils import validate_schema


def maybe_save_output_to_state(agent: Any, event: Event) -> None:
    """Save a final model text response to ``event.actions.state_delta``.

    This mirrors ADK's ``LlmAgent.__maybe_save_output_to_state`` for runtimes
    that bypass ADK's built-in LLM flow.
    """
    if event.author != agent.name:
        return

    output_key = getattr(agent, "output_key", None)
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

    result = "".join(
        part.text
        for part in event.content.parts
        if part.text and not getattr(part, "thought", False)
    )

    output_schema = getattr(agent, "output_schema", None)
    if output_schema:
        if not result.strip():
            return
        result = validate_schema(output_schema, result)

    event.actions.state_delta[output_key] = result
