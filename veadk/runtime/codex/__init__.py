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
"""

from __future__ import annotations

from typing import Any

from veadk.runtime.codex.config import CodexRuntimeConfig

__all__ = ["CodexRuntime", "CodexRuntimeConfig"]


def __getattr__(name: str) -> Any:
    if name != "CodexRuntime":
        raise AttributeError(name)
    from veadk.runtime.codex.runtime import CodexRuntime

    return CodexRuntime
