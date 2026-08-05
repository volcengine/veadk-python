"""Replaceable in-process quiet-session scheduler."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from veadk.utils.logger import get_logger

from .models import RunSseActivity

logger = get_logger(__name__)

ActivityKey = tuple[str, str, str, str]
Worker = Callable[[RunSseActivity], Awaitable[None]]
Sleep = Callable[[float], Awaitable[None]]


class QuietSessionScheduler:
    """Keep only the newest delayed task for each Studio session."""

    def __init__(
        self,
        quiet_seconds: float,
        worker: Worker,
        *,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._quiet_seconds = quiet_seconds
        self._worker = worker
        self._sleep = sleep
        self._generations: dict[ActivityKey, int] = {}
        self._tasks: dict[ActivityKey, asyncio.Task[None]] = {}

    @property
    def pending_count(self) -> int:
        return len(self._tasks)

    def invalidate(self, key: ActivityKey) -> None:
        self._generations[key] = self._generations.get(key, 0) + 1
        task = self._tasks.pop(key, None)
        if task is not None:
            task.cancel()

    def schedule(self, activity: RunSseActivity) -> None:
        key = activity.key
        self.invalidate(key)
        generation = self._generations[key]
        task = asyncio.create_task(self._run(activity, generation))
        self._tasks[key] = task

    async def _run(self, activity: RunSseActivity, generation: int) -> None:
        key = activity.key
        try:
            await self._sleep(self._quiet_seconds)
            if self._generations.get(key) != generation:
                return
            await self._worker(activity)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception(
                "automatic evaluation failed runtime_id=%s app=%s session=%s",
                activity.runtime_id,
                activity.app_name,
                activity.session_id,
            )
        finally:
            current = self._tasks.get(key)
            if current is asyncio.current_task():
                self._tasks.pop(key, None)

    async def wait_idle(self) -> None:
        while self._tasks:
            tasks = tuple(self._tasks.values())
            await asyncio.gather(*tasks, return_exceptions=True)

    async def close(self) -> None:
        tasks = tuple(self._tasks.values())
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
