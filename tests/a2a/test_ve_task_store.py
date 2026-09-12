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

"""Regression tests: `VeTaskStore` must honour the A2A `TaskStore` contract.

Two things used to be wrong. The overrides dropped the `context` parameter,
which the A2A request handlers pass *positionally*
(`await self.task_store.get(params.id, context)`), so every call raised
`TypeError`. And the bodies were `return None` stubs, so a store that did get
called would have silently discarded every task.

The signature expectations below are derived from `TaskStore` itself rather
than hardcoded, so an upstream parameter change fails these tests instead of
letting the override quietly drift out of sync again.
"""

from __future__ import annotations

import inspect

import pytest
from a2a.server.context import ServerCallContext
from a2a.server.tasks import TaskStore
from a2a.types import Task, TaskState, TaskStatus

from veadk.a2a.ve_task_store import VeTaskStore

TASK_STORE_METHODS = ["save", "get", "delete"]


def _call_contract(func) -> list[tuple]:
    """The part of a signature a caller must satisfy: name, kind, default."""
    return [
        (param.name, param.kind, param.default)
        for param in inspect.signature(func).parameters.values()
    ]


def _task(task_id: str, state: TaskState = TaskState.submitted) -> Task:
    return Task(
        id=task_id,
        context_id="test-context",
        status=TaskStatus(state=state),
    )


@pytest.mark.parametrize("method_name", TASK_STORE_METHODS)
def test_override_matches_base_call_contract(method_name: str) -> None:
    """Each override accepts exactly what the base class promises callers."""
    expected = _call_contract(getattr(TaskStore, method_name))
    actual = _call_contract(getattr(VeTaskStore, method_name))

    assert actual == expected


@pytest.mark.asyncio
async def test_context_accepted_positionally() -> None:
    """A2A's request handlers and task manager pass `context` positionally."""
    store = VeTaskStore()
    context = ServerCallContext()
    task = _task("positional-task")

    await store.save(task, context)
    assert await store.get(task.id, context) == task

    await store.delete(task.id, context)
    assert await store.get(task.id, context) is None


@pytest.mark.asyncio
async def test_context_accepted_by_keyword() -> None:
    store = VeTaskStore()
    context = ServerCallContext()
    task = _task("keyword-task")

    await store.save(task, context=context)
    assert await store.get(task.id, context=context) == task

    await store.delete(task.id, context=context)
    assert await store.get(task.id, context=context) is None


@pytest.mark.asyncio
async def test_context_is_optional() -> None:
    """`context` defaults to None, so callers may omit it entirely."""
    store = VeTaskStore()
    task = _task("no-context-task")

    await store.save(task)
    assert await store.get(task.id) == task

    await store.delete(task.id)
    assert await store.get(task.id) is None


@pytest.mark.asyncio
async def test_save_updates_existing_task() -> None:
    """Re-saving an id replaces the stored task rather than duplicating it."""
    store = VeTaskStore()
    await store.save(_task("task-1", TaskState.submitted))
    await store.save(_task("task-1", TaskState.completed))

    stored = await store.get("task-1")

    assert stored is not None
    assert stored.status.state == TaskState.completed


@pytest.mark.asyncio
async def test_get_returns_none_only_for_unknown_ids() -> None:
    """A miss must mean "absent", not "this store never returns anything"."""
    store = VeTaskStore()
    task = _task("stored-task")
    await store.save(task)

    assert await store.get("never-saved") is None
    assert await store.get(task.id) == task


@pytest.mark.asyncio
async def test_delete_of_unknown_id_leaves_other_tasks_intact() -> None:
    """Deleting a nonexistent task is tolerated and touches nothing else."""
    store = VeTaskStore()
    task = _task("survivor-task")
    await store.save(task)

    await store.delete("never-saved")

    assert await store.get(task.id) == task


@pytest.mark.asyncio
async def test_tasks_are_not_shared_between_instances() -> None:
    """Each store owns its tasks; nothing leaks through class-level state."""
    first = VeTaskStore()
    second = VeTaskStore()
    task = _task("instance-task")

    await first.save(task)

    assert await first.get(task.id) == task
    assert await second.get(task.id) is None
