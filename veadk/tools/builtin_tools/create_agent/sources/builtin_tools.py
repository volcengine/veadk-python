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

"""VeADK built-in tool resource collection."""

from __future__ import annotations

from typing import Any

from veadk.tools import list_builtin_tools
from veadk.tools.builtin_tools.create_agent.models import (
    ResourceDescriptor,
    ResourceSourceStatus,
)
from veadk.tools.builtin_tools.create_agent.resource_store import StoredResource
from veadk.tools.builtin_tools.create_agent.sources.base import SourceCollection


_TOOL_DESCRIPTIONS = {
    "coding": "Inspect and modify code in the current workspace.",
    "get_city_weather": "Get weather information for a city.",
    "get_location_weather": "Get weather information for a location.",
    "image_edit": "Edit an image from a text instruction.",
    "image_generate": "Generate an image from a text prompt.",
    "link_reader": "Read and extract content from a web link.",
    "parallel_web_search": "Run multiple web searches concurrently.",
    "ppt_generate": "Generate a presentation from structured content.",
    "run_code": "Run code with the configured VeADK code executor.",
    "text_to_speech": "Generate speech audio from text.",
    "vesearch": "Search content through the configured VeSearch service.",
    "video_generate": "Generate a video from a text or image prompt.",
    "video_task_query": "Query the status of a video generation task.",
    "web_fetch": "Fetch content from a web page.",
    "web_search": "Search the web for current information.",
}


class BuiltinToolResourceSource:
    """Expose lazily loaded VeADK tools as selectable resources."""

    name = "veadk_builtin_tools"

    async def collect(self, tool_context: Any = None) -> SourceCollection:
        del tool_context
        resources = [self._to_resource(name) for name in list_builtin_tools()]
        return SourceCollection(
            resources=resources,
            status=ResourceSourceStatus(
                source=self.name,
                status="ok",
                count=len(resources),
            ),
        )

    @staticmethod
    def _to_resource(name: str) -> StoredResource:
        descriptor = ResourceDescriptor(
            ref=f"veadk_tool:{name}",
            kind="tool",
            name=name,
            description=_TOOL_DESCRIPTIONS.get(
                name,
                "VeADK built-in tool available for dynamic agent mounting.",
            ),
            source=BuiltinToolResourceSource.name,
            metadata={"tool_name": name},
        )
        return StoredResource(descriptor=descriptor, payload=name)
