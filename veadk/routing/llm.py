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
"""Configured model pool; execution resolves a concrete adapter before preprocessing."""

from __future__ import annotations

from typing import Any

from google.adk.models.base_llm import BaseLlm
from pydantic import Field

from veadk.routing.context import get_route_selection


class RoutingLlm(BaseLlm):
    """Own the configured adapters without storing a mutable current model."""

    strong_model: BaseLlm
    runtimes: list[Any] = Field(default_factory=list)
    registry: Any = None
    store: Any = None
    classifier: Any = None
    config: Any = None
    active_runs: int = 0

    def selected_model(self, selection: Any) -> BaseLlm:
        if selection.route == "strong":
            return self.strong_model
        runtime = self.registry.get(selection.model_name)
        if runtime is None:
            raise ValueError("the fixed routing target is no longer configured")
        return runtime.llm

    async def generate_content_async(self, llm_request, stream=False):
        # Direct use remains possible; Agent resolves the concrete model earlier.
        selection = get_route_selection()
        model = self.selected_model(selection) if selection else self.strong_model
        request = llm_request.model_copy(deep=True)
        request.tools_dict = dict(llm_request.tools_dict)
        request.model = model.model
        async for response in model.generate_content_async(request, stream=stream):
            yield response
