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

from veadk.tracing.telemetry.attributes.extractors.common_attributes_extractors import (
    COMMON_ATTRIBUTES,
)
from veadk.tracing.telemetry.attributes.extractors.llm_attributes_extractors import (
    LLM_ATTRIBUTES,
)
from veadk.tracing.telemetry.attributes.extractors.tool_attributes_extractors import (
    TOOL_ATTRIBUTES,
)
from veadk.tracing.telemetry.content_tracing import should_trace_content

ATTRIBUTES = {
    "common": COMMON_ATTRIBUTES,
    "llm": LLM_ATTRIBUTES,
    "tool": TOOL_ATTRIBUTES,
}

CONTENT_ATTRIBUTES = {
    "llm": {
        "gen_ai.prompt",
        "gen_ai.completion",
        "gen_ai.messages",
        "gen_ai.choice",
    },
    "tool": {
        "gen_ai.tool.input",
        "gen_ai.tool.output",
        "cozeloop.input",
        "cozeloop.output",
        "gen_ai.input",
        "gen_ai.output",
    },
}


def get_attributes(kind: str) -> dict:
    """Return trace attributes, excluding content fields when configured."""
    attributes = ATTRIBUTES.get(kind, {})
    content_attributes = CONTENT_ATTRIBUTES.get(kind)
    if not content_attributes or should_trace_content():
        return attributes

    return {
        attr_name: attr_extractor
        for attr_name, attr_extractor in attributes.items()
        if attr_name not in content_attributes
    }
