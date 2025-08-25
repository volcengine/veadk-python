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
