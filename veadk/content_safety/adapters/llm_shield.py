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
"""Bridge the legacy agent-callback LLM Shield plugin to ADK plugins."""

from __future__ import annotations

import os
import threading
from typing import Any

from google.adk.plugins import BasePlugin

from ..config import ContentSafetyConfig

_ENV_LOCK = threading.Lock()
_APP_ID_ENV = "TOOL_LLM_SHIELD_APP_ID"


class LLMShieldPluginAdapter(BasePlugin):
    """Expose the legacy sync callbacks with ADK's keyword-only contract."""

    def __init__(self, inner: Any):
        super().__init__(name="llm_shield_adapter")
        self._inner = inner

    @classmethod
    def from_config(
        cls,
        config: ContentSafetyConfig,
        *,
        inner: Any | None = None,
    ) -> "LLMShieldPluginAdapter":
        if inner is None:
            # Imported lazily: this module has an import-time env dependency,
            # so merely selecting provider=decision must never touch it.
            from veadk.tools.builtin_tools.llm_shield import LLMShieldPlugin

            added = False
            with _ENV_LOCK:
                if config.llm_shield_app_id and not os.getenv(_APP_ID_ENV):
                    os.environ[_APP_ID_ENV] = config.llm_shield_app_id
                    added = True
                try:
                    inner = LLMShieldPlugin()
                finally:
                    if added:
                        os.environ.pop(_APP_ID_ENV, None)
        return cls(inner)

    async def before_model_callback(
        self, *, callback_context: Any, llm_request: Any, **kwargs: Any
    ) -> Any:
        return self._inner.before_model_callback(
            callback_context=callback_context, llm_request=llm_request
        )

    async def after_model_callback(
        self, *, callback_context: Any, llm_response: Any, **kwargs: Any
    ) -> Any:
        return self._inner.after_model_callback(
            callback_context=callback_context, llm_response=llm_response
        )

    async def before_tool_callback(
        self,
        *,
        tool: Any,
        tool_args: dict[str, Any],
        tool_context: Any,
        **kwargs: Any,
    ) -> Any:
        return self._inner.before_tool_callback(
            tool=tool, args=tool_args, tool_context=tool_context
        )

    async def after_tool_callback(
        self,
        *,
        tool: Any,
        tool_args: dict[str, Any],
        tool_context: Any,
        result: dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        return self._inner.after_tool_callback(
            tool=tool,
            args=tool_args,
            tool_context=tool_context,
            tool_response=result,
        )
