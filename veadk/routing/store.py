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
"""Root-invocation decision sharing."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from veadk.routing.context import RouteSelection


class RouteStore:
    """Coalesce concurrent decisions for the same root turn.

    Decisions are persisted in session state, keyed by invocation and router
    configuration. A cross-invocation cache here would conflict with the
    per-turn decision contract, so only the in-flight future is retained.
    """

    def __init__(self) -> None:
        self._inflight: dict[str, asyncio.Future[RouteSelection]] = {}

    async def get_or_create(
        self,
        key: str,
        factory: Callable[[], Awaitable[RouteSelection]],
    ) -> RouteSelection:
        """Join an in-flight decision or classify once."""

        inflight = self._inflight.get(key)
        if inflight is not None:
            return await asyncio.shield(inflight)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[RouteSelection] = loop.create_future()
        self._inflight[key] = future
        try:
            selection = await factory()
        except BaseException as exc:
            if not future.done():
                future.set_exception(exc)
                # Mark the exception as retrieved so an unawaited future does
                # not log "exception was never retrieved" at GC time.
                future.exception()
            self._inflight.pop(key, None)
            raise

        if not future.done():
            future.set_result(selection)
        self._inflight.pop(key, None)
        return selection

    def clear(self) -> None:
        """Drop in-flight state. Intended for tests and process shutdown."""

        self._inflight.clear()


_DEFAULT_STORE = RouteStore()


def get_route_store() -> RouteStore:
    """Return the process-wide route store used by Agents by default."""

    return _DEFAULT_STORE
