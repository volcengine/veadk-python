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
"""ADK ``before_model_callback`` that classifies once per invocation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from veadk.configs.routing_configs import QueryRoutingConfig
from veadk.routing.classifier import QueryClassifier
from veadk.routing.context import RouteSelection, set_route_selection
from veadk.routing.store import RouteStore

_ROUTE_STATE_KEY = "temp:veadk_query_route"


def build_before_model_callback(
    classifier: QueryClassifier,
    store: RouteStore,
    config: QueryRoutingConfig,
) -> Callable[[Any, Any], Any]:
    """Return an async callback that stores the route for the current task.

    The callback never short-circuits the model call: it returns ``None`` and
    only writes the selection into the routing context variable.
    """

    async def _before_model(callback_context: Any, llm_request: Any) -> None:
        invocation_id = getattr(callback_context, "invocation_id", "") or ""
        session = getattr(callback_context, "session", None)
        session_id = getattr(session, "id", "") or ""

        if store.session_upgraded(session_id):
            set_route_selection(
                RouteSelection(
                    route="strong",
                    reason="session_upgraded",
                    invocation_id=invocation_id,
                    session_id=session_id,
                )
            )
            return None

        state = getattr(callback_context, "state", None)
        cached = state.get(_ROUTE_STATE_KEY) if state is not None else None
        if cached == "strong":
            set_route_selection(
                RouteSelection(
                    route="strong",
                    reason="invocation_cached",
                    invocation_id=invocation_id,
                    session_id=session_id,
                )
            )
            return None
        if cached == "simple":
            runtime = classifier.registry.first_available(llm_request)
            if runtime is None:
                set_route_selection(
                    RouteSelection(
                        route="strong",
                        reason="no_capable_simple_model",
                        invocation_id=invocation_id,
                        session_id=session_id,
                    )
                )
            else:
                set_route_selection(
                    RouteSelection(
                        route="simple",
                        reason="invocation_cached",
                        invocation_id=invocation_id,
                        session_id=session_id,
                        model_name=runtime.config.name,
                    )
                )
            return None

        key = f"{config.questions_hash()}:{invocation_id or id(llm_request)}"
        selection = await store.get_or_create(
            key,
            lambda: classifier.classify(
                llm_request,
                invocation_id=invocation_id,
                session_id=session_id,
            ),
        )

        if selection.upgrade_session:
            store.upgrade_session(session_id)
        if state is not None:
            state[_ROUTE_STATE_KEY] = selection.route
        set_route_selection(selection)
        return None

    return _before_model
