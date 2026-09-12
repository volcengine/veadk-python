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

import asyncio

from a2a.server.context import ServerCallContext
from a2a.server.tasks import TaskStore
from a2a.types import Task
from typing_extensions import override

from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class VeTaskStore(TaskStore):
    """In-process implementation of the A2A `TaskStore` interface.

    Tasks are held in a dictionary owned by this instance, so they are visible
    only to the server process that stored them and are lost when it stops.

    Every method takes the `context` argument required by `TaskStore` -- the
    A2A request handlers pass it positionally -- but this store does not scope
    tasks by caller, so the value is unused.
    """

    def __init__(self) -> None:
        super().__init__()
        self._tasks: dict[str, Task] = {}
        self._lock = asyncio.Lock()

    @override
    async def save(self, task: Task, context: ServerCallContext | None = None) -> None:
        """Saves or updates a task in the store."""
        async with self._lock:
            self._tasks[task.id] = task

    @override
    async def get(
        self, task_id: str, context: ServerCallContext | None = None
    ) -> Task | None:
        """Retrieves a task from the store by ID."""
        async with self._lock:
            return self._tasks.get(task_id)

    @override
    async def delete(
        self, task_id: str, context: ServerCallContext | None = None
    ) -> None:
        """Deletes a task from the store by ID."""
        async with self._lock:
            if self._tasks.pop(task_id, None) is None:
                logger.warning(f"Attempted to delete nonexistent task: {task_id}")
