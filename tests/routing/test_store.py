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


class Clock:
    def __init__(self):
        self.now = 1_000.0

    def __call__(self):
        return self.now


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
async def test_cached_decision_is_reused_within_ttl():
    clock = Clock()
    store = RouteStore(decision_ttl=10, clock=clock)
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        return selection()

    assert await store.get_or_create("k", factory) == selection()
    clock.now += 9
    assert await store.get_or_create("k", factory) == selection()
    assert calls == 1


@pytest.mark.asyncio
async def test_expired_decision_is_reclassified():
    clock = Clock()
    store = RouteStore(decision_ttl=10, clock=clock)
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        return selection(str(calls))

    await store.get_or_create("k", factory)
    clock.now += 11
    result = await store.get_or_create("k", factory)
    assert calls == 2
    assert result.reason == "2"


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


def test_session_upgrade_expires():
    clock = Clock()
    store = RouteStore(session_ttl=10, clock=clock)
    store.upgrade_session("s1")
    assert store.session_upgraded("s1") is True
    clock.now += 11
    assert store.session_upgraded("s1") is False


def test_empty_session_never_upgrades():
    store = RouteStore()
    store.upgrade_session("")
    assert store.session_upgraded("") is False


def test_clear_drops_all_state():
    store = RouteStore()
    store.upgrade_session("s1")
    store.clear()
    assert store.session_upgraded("s1") is False


@pytest.mark.asyncio
async def test_many_entries_are_pruned_when_expired():
    clock = Clock()
    store = RouteStore(decision_ttl=10, session_ttl=10, clock=clock)

    async def factory():
        return selection()

    for index in range(4_100):
        await store.get_or_create(f"k{index}", factory)
    clock.now += 100
    await store.get_or_create("fresh", factory)
    assert len(store._decisions) == 1  # noqa: SLF001
