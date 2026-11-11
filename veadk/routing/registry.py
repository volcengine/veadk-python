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
"""Per-tier model instances and their local health state."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from google.adk.models.base_llm import BaseLlm

from veadk.configs.routing_configs import SimpleModelConfig
from veadk.routing.capability import CapabilityGuard, CapabilityCheck


@dataclass
class SimpleModelRuntime:
    """A configured cheap model and the client instance bound to it."""

    config: SimpleModelConfig
    llm: BaseLlm
    unhealthy_until: float = 0.0


@dataclass
class ModelRegistry:
    """Ordered cheap-model pool plus per-model capability/health checks.

    Selection is deterministic: the first model in configuration order that
    passes ``CapabilityGuard`` and is not circuit-broken wins. There is no
    random or round-robin dispatch.
    """

    runtimes: list[SimpleModelRuntime]
    guard: CapabilityGuard = field(default_factory=CapabilityGuard)
    _clock: Any = field(default=time.monotonic, repr=False)

    def first_available(self, llm_request: Any) -> SimpleModelRuntime | None:
        now = self._clock()
        for runtime in self.runtimes:
            if runtime.unhealthy_until > now:
                continue
            if self.guard.check(llm_request, runtime.config).allowed:
                return runtime
        return None

    def check(self, llm_request: Any, runtime: SimpleModelRuntime) -> CapabilityCheck:
        return self.guard.check(llm_request, runtime.config)

    def mark_failed(
        self, runtime: SimpleModelRuntime, *, cooldown: float = 60.0
    ) -> None:
        runtime.unhealthy_until = self._clock() + max(0.0, cooldown)

    def get(self, name: str) -> SimpleModelRuntime | None:
        for runtime in self.runtimes:
            if runtime.config.name == name:
                return runtime
        return None
