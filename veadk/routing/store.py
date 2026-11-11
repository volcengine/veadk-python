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
"""Invocation-scoped decision sharing and session stickiness."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from veadk.routing.context import RouteSelection

DEFAULT_DECISION_TTL_SECONDS = 300.0
DEFAULT_SESSION_TTL_SECONDS = 3_600.0
_MAX_ENTRIES = 4_096


class RouteStore:
    """Share one routing decision per invocation and keep sessions upgraded.

    Parallel sub-agents in the same invocation await the same in-flight
    classification instead of calling the Decision API again. The store is
    process-local; a multi-replica deployment may classify once per replica,
    which is safe but slightly more expensive.

    Session stickiness is also process-local. It only upgrades a session: once
    a request is routed to the strong model, later requests in that session
    stay there for the TTL.
    """

    def __init__(
        self,
        *,
        decision_ttl: float = DEFAULT_DECISION_TTL_SECONDS,
        session_ttl: float = DEFAULT_SESSION_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._decision_ttl = decision_ttl
        self._session_ttl = session_ttl
        self._clock = clock
        self._decisions: dict[str, tuple[float, RouteSelection]] = {}
        self._inflight: dict[str, asyncio.Future[RouteSelection]] = {}
        self._sessions: dict[str, float] = {}

    async def get_or_create(
        self,
        key: str,
        factory: Callable[[], Awaitable[RouteSelection]],
    ) -> RouteSelection:
        """Return a cached decision, join an in-flight one, or classify once."""

        self._purge()
        cached = self._decisions.get(key)
        if cached is not None:
            created_at, selection = cached
            if self._clock() - created_at <= self._decision_ttl:
                return selection
            self._decisions.pop(key, None)

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

        self._decisions[key] = (self._clock(), selection)
        self._inflight.pop(key, None)
        if not future.done():
            future.set_result(selection)
        return selection

    def upgrade_session(self, session_id: str) -> None:
        """Pin a session to the strong model until the session TTL expires."""

        if not session_id:
            return
        self._sessions[session_id] = self._clock() + self._session_ttl

    def session_upgraded(self, session_id: str) -> bool:
        """Return whether a session has already been routed to the strong model."""

        if not session_id:
            return False
        expires_at = self._sessions.get(session_id)
        if expires_at is None:
            return False
        if expires_at <= self._clock():
            self._sessions.pop(session_id, None)
            return False
        return True

    def clear(self) -> None:
        """Drop all cached state. Intended for tests and process shutdown."""

        self._decisions.clear()
        self._inflight.clear()
        self._sessions.clear()

    def _purge(self) -> None:
        if len(self._decisions) + len(self._sessions) <= _MAX_ENTRIES:
            return
        now = self._clock()
        self._decisions = {
            key: value
            for key, value in self._decisions.items()
            if now - value[0] <= self._decision_ttl
        }
        self._sessions = {
            key: expires_at
            for key, expires_at in self._sessions.items()
            if expires_at > now
        }


_DEFAULT_STORE = RouteStore()


def get_route_store() -> RouteStore:
    """Return the process-wide route store used by Agents by default."""

    return _DEFAULT_STORE
