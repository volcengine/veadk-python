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
"""Root-turn model selection propagated through nested execution.

ADK's ``BaseLlm.generate_content_async`` only receives an ``LlmRequest``, so
the invocation-scoped decision is carried in a context variable. Each ADK
invocation runs in its own asyncio task, which keeps parallel sub-agents
isolated without mutating the shared Agent.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class RouteSelection:
    """The route chosen for one root user turn."""

    route: Literal["simple", "strong"]
    reason: str
    invocation_id: str
    session_id: str = ""
    model_name: str | None = None
    shadow: bool = False
    latency_ms: float = 0.0
    input_tokens: int | None = None


@dataclass(frozen=True)
class TurnContext:
    """One immutable model binding inherited by nested execution tasks."""

    selection: RouteSelection
    model: Any
    router: Any
    target: str
    # Shared by nested tasks, owned by this root turn; the model binding stays fixed.
    tool_argument_errors: dict[str, int] = field(default_factory=dict, compare=False)


_TURN: ContextVar[TurnContext | None] = ContextVar("veadk_query_turn", default=None)


def get_turn_context() -> TurnContext | None:
    return _TURN.get()


_ROUTE_SELECTION: ContextVar[RouteSelection | None] = ContextVar(
    "veadk_route_selection", default=None
)


def set_route_selection(selection: RouteSelection | None) -> None:
    """Set the route selection for the current task."""

    _ROUTE_SELECTION.set(selection)


def get_route_selection() -> RouteSelection | None:
    """Return the route selection for the current task, if any."""

    return _ROUTE_SELECTION.get()
