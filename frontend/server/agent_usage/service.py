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

"""Non-blocking orchestration for agent usage persistence and queries."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Protocol

from pydantic import ValidationError

from veadk.utils.logger import get_logger

from .models import AgentUsageEvent, AgentUsageSummary

logger = get_logger(__name__)


class AgentUsageStorageUnavailable(RuntimeError):
    """Raised when persistent usage data cannot be queried."""


class AgentUsageRepository(Protocol):
    async def append(self, event: AgentUsageEvent) -> None: ...

    async def get_summary(
        self,
        *,
        runtime_id: str,
        app_name: str,
        page: int,
        page_size: int,
    ) -> AgentUsageSummary: ...


class AgentUsageService:
    def __init__(
        self,
        repository: AgentUsageRepository | None,
        *,
        unavailable_reason: str = "",
    ) -> None:
        self._repository = repository
        self._unavailable_reason = unavailable_reason
        self._tasks: set[asyncio.Task[None]] = set()
        self._closed = False

    @property
    def available(self) -> bool:
        return self._repository is not None

    def record_success(
        self,
        *,
        invocation_id: str,
        runtime_id: str,
        app_name: str,
        user_id: str,
        display_name: str = "",
        used_at: datetime | None = None,
    ) -> None:
        """Queue one successful invocation without delaying the response stream."""
        if self._closed or self._repository is None:
            return
        try:
            event = AgentUsageEvent(
                invocationId=invocation_id,
                runtimeId=runtime_id,
                appName=app_name,
                userId=user_id,
                displayName=display_name,
                usedAt=used_at or datetime.now(timezone.utc),
            )
            loop = asyncio.get_running_loop()
        except (RuntimeError, ValidationError) as error:
            logger.error("Invalid Studio agent usage event: %s", error)
            return
        task = loop.create_task(self._repository.append(event))
        self._tasks.add(task)
        task.add_done_callback(self._write_finished)

    async def get_summary(
        self,
        *,
        runtime_id: str,
        app_name: str,
        page: int,
        page_size: int,
    ) -> AgentUsageSummary:
        if self._repository is None:
            raise AgentUsageStorageUnavailable(self._unavailable_reason)
        return await self._repository.get_summary(
            runtime_id=runtime_id,
            app_name=app_name,
            page=page,
            page_size=page_size,
        )

    async def close(self) -> None:
        self._closed = True
        tasks = tuple(self._tasks)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    def _write_finished(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.error("Failed to persist Studio agent usage: %s", error)
