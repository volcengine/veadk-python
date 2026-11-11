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
"""Per-call route selection passed from the callback to the routing model.

ADK's ``BaseLlm.generate_content_async`` only receives an ``LlmRequest``, so
the invocation-scoped decision is carried in a context variable. Each ADK
invocation runs in its own asyncio task, which keeps parallel sub-agents
isolated without mutating the shared Agent.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RouteSelection:
    """The route chosen for one model call."""

    route: Literal["simple", "strong"]
    reason: str
    invocation_id: str
    session_id: str = ""
    model_name: str | None = None
    shadow: bool = False
    upgrade_session: bool = False


_ROUTE_SELECTION: ContextVar[RouteSelection | None] = ContextVar(
    "veadk_route_selection", default=None
)


def set_route_selection(selection: RouteSelection | None) -> None:
    """Set the route selection for the current task."""

    _ROUTE_SELECTION.set(selection)


def get_route_selection() -> RouteSelection | None:
    """Return the route selection for the current task, if any."""

    return _ROUTE_SELECTION.get()
