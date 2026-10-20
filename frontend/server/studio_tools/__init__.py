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

"""Studio BFF-owned dynamic tools and the Runtime WebSocket bridge."""

from __future__ import annotations

import importlib
from typing import Any


_EXPORT_MODULES = {
    "AgentkitEnvironmentSandboxResolver": "sandbox_shell",
    "CodexSandboxConnection": "codex_sandbox",
    "CodexSandboxDelegate": "codex_sandbox",
    "LocalStudioToolDispatcher": "local",
    "SandboxExecutionTarget": "sandbox_shell",
    "SandboxResolutionError": "sandbox_shell",
    "SandboxTargetResolver": "sandbox_shell",
    "StudioChannelError": "connector",
    "StudioTool": "registry",
    "StudioToolCatalogSnapshot": "registry",
    "StudioToolExecutionContext": "registry",
    "StudioToolRegistry": "registry",
    "StudioToolRun": "connector",
    "StudioToolRuntimeError": "registry",
    "build_local_studio_tools": "local",
    "build_studio_tool_registry": "registry",
    "ensure_local_studio_toolset": "local",
    "execute_in_sandbox": "sandbox_shell",
    "local_progress_sse_event": "local",
    "open_studio_tool_run": "connector",
    "register_codex_sandbox_tool": "codex_sandbox",
    "register_sandbox_shell_tool": "sandbox_shell",
    "runtime_supports_bff_tools": "connector",
    "stream_local_studio_response": "local",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(f"{__name__}.{module_name}")
    value = getattr(module, name)
    globals()[name] = value
    return value


__all__ = [
    "AgentkitEnvironmentSandboxResolver",
    "CodexSandboxConnection",
    "CodexSandboxDelegate",
    "SandboxExecutionTarget",
    "SandboxResolutionError",
    "SandboxTargetResolver",
    "LocalStudioToolDispatcher",
    "StudioChannelError",
    "StudioTool",
    "StudioToolCatalogSnapshot",
    "StudioToolExecutionContext",
    "StudioToolRegistry",
    "StudioToolRun",
    "StudioToolRuntimeError",
    "build_studio_tool_registry",
    "build_local_studio_tools",
    "ensure_local_studio_toolset",
    "execute_in_sandbox",
    "local_progress_sse_event",
    "open_studio_tool_run",
    "register_codex_sandbox_tool",
    "register_sandbox_shell_tool",
    "runtime_supports_bff_tools",
    "stream_local_studio_response",
]
