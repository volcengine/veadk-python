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

import pytest

from veadk.routing.context import RouteSelection
from veadk.routing.store import RouteStore


def selection(reason="ok"):
    return RouteSelection(route="simple", reason=reason, invocation_id="inv")


@pytest.mark.asyncio
async def test_concurrent_callers_share_one_classification():
    store = RouteStore()
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def factory():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return selection()

    first = asyncio.create_task(store.get_or_create("k", factory))
    await started.wait()
    second = asyncio.create_task(store.get_or_create("k", factory))
    await asyncio.sleep(0)
    release.set()

    results = await asyncio.gather(first, second)
    assert calls == 1
    assert results[0] == results[1]


@pytest.mark.asyncio
async def test_completed_decision_is_not_cached_across_calls():
    store = RouteStore()
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        return selection(str(calls))

    first = await store.get_or_create("k", factory)
    second = await store.get_or_create("k", factory)
    assert first.reason == "1"
    assert second.reason == "2"
    assert calls == 2
    assert store._inflight == {}


@pytest.mark.asyncio
async def test_factory_failure_propagates_and_clears_inflight():
    store = RouteStore()

    async def failing():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await store.get_or_create("k", failing)

    async def ok():
        return selection()

    assert await store.get_or_create("k", ok) == selection()
    assert store._inflight == {}


@pytest.mark.asyncio
async def test_cancelled_classification_clears_inflight():
    store = RouteStore()
    started = asyncio.Event()

    async def wait_forever():
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(store.get_or_create("k", wait_forever))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert store._inflight == {}


@pytest.mark.asyncio
async def test_clear_drops_inflight_state():
    store = RouteStore()
    store._inflight["k"] = asyncio.get_running_loop().create_future()
    store.clear()
    assert store._inflight == {}
