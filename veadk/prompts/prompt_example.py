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

from typing import Any, Union
from pydantic import BaseModel, Field
from google.genai import types
from google.adk.examples.example import Example


# === Add these classes before the Agent class ===
class FunctionCallExample(BaseModel):
    """Represents a function call output in an example."""

    func_name: str
    func_args: dict[str, Any] = Field(default_factory=dict)


class AgentExample(BaseModel):
    """A few-shot example for the agent.

    Attributes:
        input: User input text.
        output: Expected output - text string or function call.
    """

    input: str
    output: Union[str, FunctionCallExample]


def _convert_to_adk_examples(examples: list[AgentExample]) -> list[Example]:
    """Convert AgentExample list to ADK Example list."""
    result = []
    for ex in examples:
        input_content = types.Content(
            role="user", parts=[types.Part.from_text(text=ex.input)]
        )
        if isinstance(ex.output, str):
            output_parts = [types.Part.from_text(text=ex.output)]
        else:
            output_parts = [
                types.Part.from_function_call(
                    name=ex.output.func_name, args=ex.output.func_args
                )
            ]
        output_content = [types.Content(role="model", parts=output_parts)]
        result.append(Example(input=input_content, output=output_content))
    return result
