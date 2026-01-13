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

from typing import Any

from google.adk.examples.base_example_provider import BaseExampleProvider
from google.adk.examples.example import Example as ADKExample
from google.genai.types import Content, FunctionCall, Part
from pydantic import BaseModel, Field
from typing_extensions import override


class ExampleFunctionCall(BaseModel):
    function_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Example(BaseModel):
    input: str
    expected_output: str | None
    expected_function_call: ExampleFunctionCall | None


class InMemoryExampleStore(BaseExampleProvider):
    def __init__(
        self,
        name: str = "in_memory_example_store",
        examples: list[Example | ADKExample] | None = None,
    ):
        self.name = name
        if examples:
            self.examples: list[ADKExample] = self.convert_examples_to_adk_examples(
                examples
            )
        else:
            self.examples: list[ADKExample] = []

    def add_example(self, example: Example | ADKExample):
        """Add an example to the provider.

        Args:
            example: A VeADK example or ADK example.
        """
        self.examples.append(self.convert_examples_to_adk_examples([example])[0])

    def convert_examples_to_adk_examples(
        self,
        examples: list[Example | ADKExample],
    ) -> list[ADKExample]:
        """Convert VeADK example to ADK example.

        Args:
            examples: A list of VeADK example or ADK example.

        Returns:
            A list of ADK example.
        """
        adk_examples = []
        for example in examples:
            if isinstance(example, ADKExample):
                adk_examples.append(example)
            else:
                output_string_content = (
                    Content(parts=[Part(text=example.expected_output)], role="model")
                    if example.expected_output
                    else None
                )
                output_fc_content = (
                    Content(
                        parts=[
                            Part(
                                function_call=FunctionCall(
                                    name=example.expected_function_call.function_name,
                                    args=example.expected_function_call.arguments,
                                )
                            )
                        ],
                        role="model",
                    )
                    if example.expected_function_call
                    else None
                )

                output = []
                if output_string_content:
                    output.append(output_string_content)
                if output_fc_content:
                    output.append(output_fc_content)

                adk_examples.append(
                    ADKExample(
                        input=Content(parts=[Part(text=example.input)], role="user"),
                        output=output,
                    )
                )
        return adk_examples

    @override
    def get_examples(self, query: str) -> list[ADKExample]:
        """Simply return all examples.

        Args:
            query: The query to get examples for.

        Returns:
            A list of Example objects.
        """
        return self.examples
