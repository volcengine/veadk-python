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

from veadk.tracing.telemetry.attributes.extractors.types import (
    ExtractorResponse,
    ToolAttributesParams,
)
from veadk.utils.misc import safe_json_serialize


def tool_gen_ai_operation_name(params: ToolAttributesParams) -> ExtractorResponse:
    return ExtractorResponse(content="execute_tool")

def tool_gen_ai_span_kind(params: ToolAttributesParams) -> ExtractorResponse:
    return ExtractorResponse(content="tool")


def tool_gen_ai_tool_message(params: ToolAttributesParams) -> ExtractorResponse:
    tool_input = {
        "role": "tool",
        "content": safe_json_serialize(
            {
                "name": params.tool.name,
                "description": params.tool.description,
                "parameters": params.args,
            }
        ),
    }
    return ExtractorResponse(type="event", content=tool_input)


def tool_gen_ai_tool_input(params: ToolAttributesParams) -> ExtractorResponse:
    tool_input = {
        "name": params.tool.name,
        "description": params.tool.description,
        "parameters": params.args,
    }
    return ExtractorResponse(
        content=safe_json_serialize(tool_input) or "<unknown_tool_input>"
    )


def tool_gen_ai_tool_name(params: ToolAttributesParams) -> ExtractorResponse:
    return ExtractorResponse(content=params.tool.name or "<unknown_tool_name>")


def tool_gen_ai_tool_output(params: ToolAttributesParams) -> ExtractorResponse:
    function_response = params.function_response_event.get_function_responses()[
        0
    ].model_dump()
    tool_output = {
        "id": function_response["id"],
        "name": function_response["name"],
        "response": function_response["response"],
    }
    return ExtractorResponse(
        content=safe_json_serialize(tool_output) or "<unknown_tool_output>"
    )


TOOL_ATTRIBUTES = {
    "gen_ai.operation.name": tool_gen_ai_operation_name,
    "gen_ai.tool.name": tool_gen_ai_tool_name,  # TLS required
    "gen_ai.tool.input": tool_gen_ai_tool_input,  # TLS required
    "gen_ai.tool.output": tool_gen_ai_tool_output,  # TLS required
    "cozeloop.input": tool_gen_ai_tool_input,  # CozeLoop required
    "cozeloop.output": tool_gen_ai_tool_output,  # CozeLoop required
    "gen_ai.span.kind": tool_gen_ai_span_kind,  # apmplus required
    "gen_ai.input": tool_gen_ai_tool_input,  # apmplus required
    "gen_ai.output": tool_gen_ai_tool_output,  # apmplus required
}
