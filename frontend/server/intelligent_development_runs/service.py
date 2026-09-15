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

"""Own task workers independently of HTTP subscribers."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

from veadk.utils.logger import get_logger

from .models import Run
from .repository import RunLeaseLost, RunRepository

logger = get_logger(__name__)


class RunService:
    def __init__(
        self, repository: RunRepository, execute: Callable[[Run, str], Awaitable[None]]
    ) -> None:
        self.repository = repository
        self.execute = execute
        self._workers: dict[tuple[str, str], asyncio.Task[None]] = {}
        self._scheduler: asyncio.Task[None] | None = None
        self._closing = False
        self.poll_interval = 0.25
        self.heartbeat_seconds = 10.0

    async def start(self) -> None:
        self._closing = False
        if self._scheduler is None or self._scheduler.done():
            self._scheduler = asyncio.create_task(
                self._schedule(), name="development-run-scheduler"
            )

    async def _schedule(self) -> None:
        while not self._closing:
            try:
                for run in await self.repository.recoverable():
                    if (
                        self.repository.clock() - run.created_at
                        >= self.repository.max_active_seconds
                    ):
                        run = await self.repository.request_stop(run.owner_id, run.id)
                    self.launch(run)
                await self.repository.cleanup()
            except Exception as error:
                logger.error(
                    "Development scheduler failed error_type=%s", type(error).__name__
                )
            await asyncio.sleep(2)

    def launch(self, run: Run) -> None:
        key = (run.owner_id, run.id)
        if self._closing or run.terminal:
            return
        if sum(not worker.done() for worker in self._workers.values()) >= 16:
            return
        previous = self._workers.get(key)
        if previous is not None and not previous.done():
            return
        self._workers[key] = asyncio.create_task(
            self._work(run), name=f"development-run-{run.id}"
        )

    async def _work(self, run: Run) -> None:
        token = await self.repository.claim(run.owner_id, run.id)
        if token is None:
            self._workers.pop((run.owner_id, run.id), None)
            return
        work = asyncio.ensure_future(self.execute(run, token))
        heartbeat = asyncio.create_task(self._heartbeat(run, token))
        try:
            done, _ = await asyncio.wait(
                {work, heartbeat}, return_when=asyncio.FIRST_COMPLETED
            )
            if heartbeat in done:
                # A lost lease must stop this worker before it dispatches more RPCs.
                await heartbeat
            await work
        except RunLeaseLost:
            logger.warning("Development executor lease lost run_id=%s", run.id)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.error(
                "Development worker failed run_id=%s error_type=%s",
                run.id,
                type(error).__name__,
            )
            with contextlib.suppress(RunLeaseLost):
                current = await self.repository.get(run.owner_id, run.id)
                if not current.terminal:
                    await self.repository.update(
                        run.owner_id,
                        run.id,
                        token,
                        state="stopping" if current.stop_requested else "waiting_user",
                        state_message="任务状态暂时无法确认，已保留输出，请稍后恢复。",
                    )
        finally:
            for task in (work, heartbeat):
                task.cancel()
            await asyncio.gather(work, heartbeat, return_exceptions=True)
            await self.repository.release(run.owner_id, run.id, token)
            self._workers.pop((run.owner_id, run.id), None)

    async def _heartbeat(self, run: Run, token: str) -> None:
        while True:
            await asyncio.sleep(5)
            await self.repository.heartbeat(run.owner_id, run.id, token)

    async def stop(self, owner: str, run_id: str) -> Run:
        run = await self.repository.request_stop(owner, run_id)
        self.launch(run)
        return run

    async def resume(self, owner: str, run_id: str) -> Run:
        run = await self.repository.resume(owner, run_id)
        self.launch(run)
        return run

    async def subscribe(
        self, owner: str, run_id: str, *, after: int = 0
    ) -> AsyncGenerator[dict[str, Any] | None, None]:
        # Authorization must happen before StreamingResponse sends HTTP headers.
        await self.repository.get(owner, run_id)
        cursor = after
        quiet = 0
        while True:
            events = await self.repository.events(owner, run_id, after=cursor)
            for event in events:
                cursor = event["seq"]
                yield event
            run = await self.repository.get(owner, run_id)
            if (run.terminal or run.state == "waiting_user") and cursor >= run.last_seq:
                return
            if events:
                quiet = 0
                continue
            await asyncio.sleep(self.poll_interval)
            quiet += self.poll_interval
            if quiet >= self.heartbeat_seconds:
                quiet = 0
                yield None

    async def close(self) -> None:
        """Detach workers for shutdown; only an explicit stop interrupts Codex."""
        self._closing = True
        if self._scheduler is not None:
            self._scheduler.cancel()
            await asyncio.gather(self._scheduler, return_exceptions=True)
        workers = tuple(self._workers.values())
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        self._workers.clear()
