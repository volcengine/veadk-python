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
"""Local, deterministic capability checks before downgrading a request."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from veadk.configs.routing_configs import SimpleModelConfig
from veadk.routing.state import request_has_media, request_text_chars


@dataclass(frozen=True)
class CapabilityCheck:
    """Whether a cheap model can serve one request."""

    allowed: bool
    reason: str = ""


class CapabilityGuard:
    """Reject a cheap model when the request needs more than it declares.

    Unknown capability is denied by default. This is a hard, local gate: it
    never calls the Decision API and never depends on model-name heuristics.
    """

    def check(
        self,
        llm_request: Any,
        model: SimpleModelConfig,
    ) -> CapabilityCheck:
        if request_has_media(llm_request) and not model.supports_media:
            return CapabilityCheck(False, "media_not_supported")

        if self._has_tools(llm_request) and not model.supports_tools:
            return CapabilityCheck(False, "tools_not_supported")

        if (
            self._has_structured_output(llm_request)
            and not model.supports_structured_output
        ):
            return CapabilityCheck(False, "structured_output_not_supported")

        if request_text_chars(llm_request) > model.max_context_chars:
            return CapabilityCheck(False, "context_too_large")

        return CapabilityCheck(True)

    @staticmethod
    def _has_tools(llm_request: Any) -> bool:
        if getattr(llm_request, "tools_dict", None):
            return True
        config = getattr(llm_request, "config", None)
        return bool(getattr(config, "tools", None))

    @staticmethod
    def _has_structured_output(llm_request: Any) -> bool:
        config = getattr(llm_request, "config", None)
        for field in ("response_schema", "response_json_schema", "output_schema"):
            if getattr(config, field, None) is not None:
                return True
        return False
