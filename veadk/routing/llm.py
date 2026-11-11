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
"""A per-call ``BaseLlm`` proxy over prebuilt strong and cheap models.

The proxy exists because ``thinking`` and ``caching`` are model-level
parameters: one model instance per tier is built once, and each call is
delegated to the instance chosen by the routing callback. No shared Agent
field is mutated, so concurrent sessions cannot race.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from pydantic import ConfigDict, Field
from typing_extensions import override

from veadk.routing.context import get_route_selection
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class RoutingLlm(BaseLlm):
    """Delegate each call to the strong or first-capable cheap model."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    model: str
    strong_model: BaseLlm
    runtimes: list[Any] = Field(default_factory=list)
    registry: Any = None
    store: Any = None

    @override
    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        selection = get_route_selection()

        if selection is None or selection.route != "simple":
            async for response in self.strong_model.generate_content_async(
                self._request_for(self.strong_model, llm_request),
                stream=stream,
            ):
                yield response
            return

        runtime = (
            self.registry.get(selection.model_name)
            if self.registry is not None and selection.model_name
            else None
        )
        if runtime is None:
            async for response in self.strong_model.generate_content_async(
                self._request_for(self.strong_model, llm_request),
                stream=stream,
            ):
                yield response
            return

        emitted = False
        try:
            async for response in runtime.llm.generate_content_async(
                self._request_for(runtime.llm, llm_request),
                stream=stream,
            ):
                emitted = True
                yield response
            return
        except Exception as exc:
            if emitted:
                # Once any chunk is visible a retry could duplicate output.
                raise
            logger.warning(
                "query routing simple model failed before first chunk: "
                "model=%s error=%s; falling back to strong model",
                runtime.config.name,
                type(exc).__name__,
            )
            if self.registry is not None and self._is_capability_error(exc):
                self.registry.mark_failed(runtime)
            if self.store is not None and selection.session_id:
                self.store.upgrade_session(selection.session_id)

        async for response in self.strong_model.generate_content_async(
            self._request_for(self.strong_model, llm_request),
            stream=stream,
        ):
            yield response

    @staticmethod
    def _request_for(model: BaseLlm, llm_request: LlmRequest) -> LlmRequest:
        """Return a request whose ``model`` matches the delegated instance.

        ADK's LiteLlm prefers ``llm_request.model`` over the instance's own
        model, so leaving the strong model name in place would silently call
        the wrong tier.
        """

        target = getattr(model, "model", None)
        if not target or llm_request.model == target:
            return llm_request
        request = llm_request.model_copy(deep=False)
        request.model = target
        return request

    @staticmethod
    def _is_capability_error(error: BaseException) -> bool:
        candidates = (
            getattr(error, "status_code", None),
            getattr(getattr(error, "response", None), "status_code", None),
        )
        for value in candidates:
            try:
                if int(value) in {400, 404}:
                    return True
            except (TypeError, ValueError):
                continue
        return False
