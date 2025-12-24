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

from dataclasses import dataclass
from typing import Any, Union


@dataclass
class FunctionCallExample:
    """Function call output example."""

    func_name: str
    func_args: dict[str, Any]


@dataclass
class AgentExample:
    """Input/output example for agent instruction."""

    input: str
    output: Union[str, FunctionCallExample]


def format_examples(examples: list[AgentExample]) -> str:
    """Format examples as natural language string."""
    if not examples:
        return ""

    lines = ["\n\n# Input/Output Example"]
    for i, ex in enumerate(examples, 1):
        lines.append(f"\nExample {i}:")
        lines.append(f"- Input: {ex.input}")
        if isinstance(ex.output, str):
            lines.append(f"- Output: {ex.output}")
        else:
            lines.append(
                f"- Output: Call function `{ex.output.func_name}` with arguments {ex.output.func_args}"
            )

    return "\n".join(lines)
