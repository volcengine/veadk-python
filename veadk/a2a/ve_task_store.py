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

from a2a.server.tasks import TaskStore
from a2a.types import Task
from typing_extensions import override


class VeTaskStore(TaskStore):
    def __init__(self):
        super().__init__()

    @override
    async def save(self, task: Task) -> None:
        """Saves or updates a task in the store."""
        return None

    @override
    async def get(self, task_id: str) -> Task | None:
        """Retrieves a task from the store by ID."""
        return None

    @override
    async def delete(self, task_id: str) -> None:
        """Deletes a task from the store by ID."""
        return None
