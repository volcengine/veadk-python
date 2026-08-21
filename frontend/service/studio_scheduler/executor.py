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

"""Thin provider selection boundary shared by Volcengine and BytePlus."""

from __future__ import annotations

from collections.abc import Iterable

from .models import ExecutionRequest, ExecutionResult, ProviderName
from .ports import CancellationControl, RuntimeProvider


class ProviderRuntimeExecutor:
    """Delegate to a provider adapter that owns service-identity resolution."""

    def __init__(self, providers: Iterable[RuntimeProvider]) -> None:
        self._providers: dict[ProviderName, RuntimeProvider] = {
            provider.provider: provider for provider in providers
        }

    async def execute(
        self, request: ExecutionRequest, control: CancellationControl
    ) -> ExecutionResult:
        try:
            provider = self._providers[request.runtime.provider]
        except KeyError as error:
            raise ValueError(
                f"Runtime provider is not configured: {request.runtime.provider}"
            ) from error
        return await provider.execute(request, control)
