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

"""Adapters between Google ADK content objects and Harness schemas."""

from __future__ import annotations

from collections.abc import Iterable

from google.adk.models import LlmRequest
from google.genai import types

from veadk.extensions.harness.schemas import ConversationMessage
from veadk.extensions.harness.utils import stringify_json_value


def content_to_text(content: types.Content | None) -> str:
    """Extract text-like content from a Google GenAI Content object."""

    if content is None or not content.parts:
        return ""
    values: list[str] = []
    for part in content.parts:
        if part.text:
            values.append(part.text)
        elif part.function_response is not None:
            values.append(stringify_json_value(part.function_response.model_dump()))
        elif part.function_call is not None:
            values.append(stringify_json_value(part.function_call.model_dump()))
        elif part.executable_code is not None:
            values.append(part.executable_code.code or "")
        elif part.code_execution_result is not None:
            values.append(stringify_json_value(part.code_execution_result.model_dump()))
    return "\n".join(value for value in values if value)


def contents_to_messages(
    contents: Iterable[types.Content],
) -> list[ConversationMessage]:
    """Project ADK contents into protocol-neutral Harness messages."""

    messages = []
    for content in contents:
        text = content_to_text(content)
        if not text:
            continue
        messages.append(
            ConversationMessage(role=content.role or "unknown", content=text)
        )
    return messages


def append_system_instruction(llm_request: LlmRequest, instruction: str) -> None:
    """Append Harness context to the model system instruction."""

    existing = llm_request.config.system_instruction
    if not existing:
        llm_request.config.system_instruction = instruction
        return
    if isinstance(existing, str):
        llm_request.config.system_instruction = f"{existing}\n\n{instruction}"
        return
    existing_text = _system_instruction_to_text(existing)
    if existing_text:
        llm_request.config.system_instruction = f"{existing_text}\n\n{instruction}"
    else:
        llm_request.config.system_instruction = instruction


def response_text(content: types.Content | None) -> str:
    """Extract final response text."""

    return content_to_text(content)


def text_response(text: str) -> types.Content:
    """Build a model response content from text."""

    return types.Content(role="model", parts=[types.Part(text=text)])


def _system_instruction_to_text(value: object) -> str:
    if isinstance(value, types.Content):
        return content_to_text(value)
    if isinstance(value, types.Part):
        return value.text or stringify_json_value(value.model_dump())
    if isinstance(value, list):
        values = [_system_instruction_to_text(item) for item in value]
        return "\n".join(item for item in values if item)
    return stringify_json_value(value)
