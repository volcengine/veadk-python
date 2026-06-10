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

import importlib

from google.adk.agents.llm_agent import ToolUnion

from veadk.tools.demo_tools import get_city_weather, get_location_weather

# Common built-in tools addressable by name, for dynamic mounting (e.g. a
# harness spec listing tool names). Values are "module:attr" import paths so
# importing this package does NOT eagerly pull each tool's dependencies — some
# tools (e.g. image/video generation) build a client at import time and require
# credentials. They are resolved lazily on first use via get_builtin_tool().
_BUILTIN_TOOLS: dict[str, str] = {
    # Web
    "web_search": "veadk.tools.builtin_tools.web_search:web_search",
    "web_fetch": "veadk.tools.builtin_tools.web_fetch:web_fetch",
    "parallel_web_search": "veadk.tools.builtin_tools.parallel_web_search:parallel_web_search",
    "vesearch": "veadk.tools.builtin_tools.vesearch:vesearch",
    "link_reader": "veadk.tools.builtin_tools.link_reader:link_reader",
    # Code
    "run_code": "veadk.tools.builtin_tools.run_code:run_code",
    "coding": "veadk.tools.builtin_tools.coding:coding",
    # Image / video / speech generation
    "image_generate": "veadk.tools.builtin_tools.image_generate:image_generate",
    "image_edit": "veadk.tools.builtin_tools.image_edit:image_edit",
    "video_generate": "veadk.tools.builtin_tools.video_generate:video_generate",
    "text_to_speech": "veadk.tools.builtin_tools.tts:text_to_speech",
}


def list_builtin_tools() -> list[str]:
    """Names of the built-in tools that can be referenced by name."""
    return sorted(_BUILTIN_TOOLS)


def get_builtin_tool(name: str) -> ToolUnion:
    """Resolve a built-in tool by name to its callable.

    Raises:
        KeyError: if ``name`` is not a known built-in tool.
    """
    if name not in _BUILTIN_TOOLS:
        raise KeyError(
            f"Unknown built-in tool '{name}'. "
            f"Available: {', '.join(list_builtin_tools())}"
        )
    module_path, attr = _BUILTIN_TOOLS[name].split(":")
    module = importlib.import_module(module_path)
    return getattr(module, attr)


__all__ = [
    "get_city_weather",
    "get_location_weather",
    "get_builtin_tool",
    "list_builtin_tools",
]
