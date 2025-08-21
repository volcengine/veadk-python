from veadk.tracing.telemetry.attributes.extractors.common_attributes_extractors import (
    COMMON_ATTRIBUTES,
)
from veadk.tracing.telemetry.attributes.extractors.llm_attributes_extractors import (
    LLM_ATTRIBUTES,
)
from veadk.tracing.telemetry.attributes.extractors.tool_attributes_extractors import (
    TOOL_ATTRIBUTES,
)

ATTRIBUTES = {
    "common": COMMON_ATTRIBUTES,
    "llm": LLM_ATTRIBUTES,
    "tool": TOOL_ATTRIBUTES,
}
