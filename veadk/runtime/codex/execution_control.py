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

"""Cancellation and admission controls shared by Codex transports."""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections.abc import Iterator


class CodexToolIterationLimitError(RuntimeError):
    """A turn exhausted its ADK tool call budget before execution."""


class TurnRequests:
    """Own the requests of one turn, including across event loops.

    Revocation is synchronous, so no new work can enter after unregistering.
    The runtime also drains the cancelled requests before closing toolsets.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._closed = False
        self._tasks: set[asyncio.Task] = set()

    def check_active(self) -> None:
        with self._lock:
            if self._closed:
                raise asyncio.CancelledError("Codex turn was closed")

    @contextlib.contextmanager
    def track(self) -> Iterator[None]:
        task = asyncio.current_task()
        assert task is not None
        with self._lock:
            if self._closed:
                raise asyncio.CancelledError("Codex turn was closed")
            self._tasks.add(task)
        try:
            yield
        finally:
            with self._lock:
                self._tasks.discard(task)

    def cancel(self) -> tuple[asyncio.Task, ...]:
        with self._lock:
            self._closed = True
            tasks = tuple(self._tasks)
        for task in tasks:
            loop = task.get_loop()
            if not loop.is_closed():
                loop.call_soon_threadsafe(task.cancel)
        return tasks

    @staticmethod
    async def drain(tasks: tuple[asyncio.Task, ...]) -> None:
        async def join(task: asyncio.Task) -> None:
            await asyncio.gather(task, return_exceptions=True)

        current_loop = asyncio.get_running_loop()
        waits = []
        for task in tasks:
            loop = task.get_loop()
            if task.done() or loop.is_closed():
                continue
            if loop is current_loop:
                waits.append(join(task))
            else:
                waits.append(
                    asyncio.wrap_future(
                        asyncio.run_coroutine_threadsafe(join(task), loop)
                    )
                )
        await asyncio.gather(*waits)
