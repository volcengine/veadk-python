from veadk.tracing.telemetry.attributes.extractors.types import (
    ExtractorResponse,
    ToolAttributesParams,
)


def tool_gen_ai_operation_name(params: ToolAttributesParams) -> ExtractorResponse:
    return ExtractorResponse(content="execute_tool")


TOOL_ATTRIBUTES = {
    "gen_ai.operation.name": tool_gen_ai_operation_name,
}
