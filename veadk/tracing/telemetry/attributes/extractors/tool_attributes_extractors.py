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

import json

from veadk.tracing.telemetry.attributes.extractors.types import (
    ExtractorResponse,
    ToolAttributesParams,
)


def tool_gen_ai_operation_name(params: ToolAttributesParams) -> ExtractorResponse:
    return ExtractorResponse(content="execute_tool")


def tool_gen_ai_tool_message(params: ToolAttributesParams) -> ExtractorResponse:
    tool_input = {
        "id": "123",
        "role": "tool",
        "content": json.dumps(
            {
                "name": params.tool.name,
                "description": params.tool.description,
                "parameters": params.args,
            }
        ),
    }
    return ExtractorResponse(type="event", content=tool_input)


# def tool_gen_ai_tool_message(params: ToolAttributesParams) -> ExtractorResponse:
#     # tool_output = {
#     #     "id": params.function_response_event.,
#     #     "name": ...,
#     #     "response": ...,
#     # }
#     print(params.function_response_event)
#     # return ExtractorResponse(content=json.dumps(tool_output) or "<unknown_tool_output>")


TOOL_ATTRIBUTES = {
    "gen_ai.operation.name": tool_gen_ai_operation_name,
    "gen_ai.tool.message": tool_gen_ai_tool_message,
}
