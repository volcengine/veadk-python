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

"""OpenAI Codex SDK runtime.

The implementation is imported lazily so configuration, translation, and tool
bridge helpers remain usable when the optional ``openai-codex`` SDK is absent.

:func:`current_workspace` is deliberately *not* lazy: an ADK tool imports it to
find the directory the sandbox is working in, and that tool module has to stay
importable in processes where the Codex SDK is not installed (the same tool is
routinely run by other runtimes, and by unit tests).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from veadk.runtime.codex.config import CodexRuntimeConfig
from veadk.runtime.codex.workspace import current_workspace

if TYPE_CHECKING:
    from veadk.runtime.codex.runtime import CodexRuntime
    from veadk.runtime.codex.runtime import release_codex_session
    from veadk.runtime.codex.runtime import shutdown_codex_runtime
    from veadk.runtime.codex.turn_control import CodexTurnAdmissionTimeout

__all__ = [
    "CodexRuntime",
    "CodexRuntimeConfig",
    "CodexTurnAdmissionTimeout",
    "current_workspace",
    "release_codex_session",
    "shutdown_codex_runtime",
]

_RUNTIME_LAZY = ("CodexRuntime", "release_codex_session", "shutdown_codex_runtime")
_TURN_CONTROL_LAZY = ("CodexTurnAdmissionTimeout",)


def __getattr__(name: str) -> Any:
    if name in _RUNTIME_LAZY:
        from veadk.runtime.codex import runtime

        return getattr(runtime, name)
    if name in _TURN_CONTROL_LAZY:
        from veadk.runtime.codex import turn_control

        return getattr(turn_control, name)
    raise AttributeError(name)
