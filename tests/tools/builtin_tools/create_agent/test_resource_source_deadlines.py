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

"""Wall-clock deadlines on the paginated create-agent resource sweeps.

Two things are pinned here:

1. a breached sweep returns what it collected with ``status="error"`` -- never
   an exception, and never ``status="ok"`` over a truncated list;
2. that verdict belongs to one ``collect()`` call. The toolset builds each
   source once and outlives every session, and ``collect_resources`` fans the
   sources out with ``asyncio.gather``, so overlapping sweeps on a single
   source object are the normal case. A deadline kept on the instance lets one
   call answer for the other -- a partial list passed off as complete is
   exactly what makes the model conclude a resource does not exist.
"""

from __future__ import annotations

import asyncio
import contextvars
import threading
from types import SimpleNamespace

import pytest

from veadk.tools.builtin_tools.create_agent.sources import (
    AgentKitKnowledgeSource,
    AgentKitSkillCenterSource,
    CloudCredentials,
)
from veadk.tools.builtin_tools.create_agent.sources import (
    agentkit_knowledge as knowledge_module,
)
from veadk.tools.builtin_tools.create_agent.sources import skills as skills_module

_KNOWLEDGE_BUDGET = knowledge_module._SWEEP_DEADLINE_SECONDS
_SKILLS_BUDGET = skills_module._SWEEP_DEADLINE_SECONDS

# Every wait below is bounded, so a regression fails the test instead of
# hanging the suite.
_TIMEOUT = 5.0

_SOLO = "solo"
_BREACHING = "breaching"
_CLEAN = "clean"

_CURRENT_CALL: contextvars.ContextVar[str] = contextvars.ContextVar(
    "collect_call", default=_SOLO
)


class _CallClock:
    """A ``time.monotonic`` stand-in whose reading depends on who asks.

    A ContextVar tells overlapping ``collect()`` calls apart: both
    ``asyncio.to_thread`` and ``asyncio.gather`` copy the calling context, so a
    call's coroutine and its paginating worker threads all read the same clock.
    One call can then outrun its budget while the other stays inside its own.
    """

    def __init__(self) -> None:
        self._readings: dict[str, float] = {}

    def set(self, call: str, seconds: float) -> None:
        self._readings[call] = seconds

    def monotonic(self) -> float:
        return self._readings.get(_CURRENT_CALL.get(), 0.0)


def _use_clock(monkeypatch, module, clock: _CallClock) -> None:
    """The sweeps only ever read ``monotonic``, so that is all the fake needs."""
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=clock.monotonic))


class _Gate:
    """Parks one sweep inside its worker thread until the test releases it."""

    def __init__(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._released = threading.Event()
        self.entered = asyncio.Event()

    def enter(self) -> None:
        """Called on a worker thread: hand control back, then wait."""
        self._loop.call_soon_threadsafe(self.entered.set)
        if not self._released.wait(_TIMEOUT):
            raise AssertionError("the parked sweep was never released")

    def release(self) -> None:
        self._released.set()

    async def wait_entered(self) -> None:
        await asyncio.wait_for(self.entered.wait(), _TIMEOUT)


def _credentials(tool_context=None) -> CloudCredentials:
    return CloudCredentials("ak", "sk", "sts")


async def _collect_as(call: str, source):
    """Run one ``collect()`` under its own clock label."""
    _CURRENT_CALL.set(call)
    return await source.collect()


def _knowledge_page(index: int, next_token: str) -> SimpleNamespace:
    return SimpleNamespace(
        knowledge_bases=[
            SimpleNamespace(
                knowledge_id=f"kb-{index}",
                provider_knowledge_id=f"provider_{index}",
                provider_type="VIKINGDB_KNOWLEDGE",
                name=f"handbook-{index}",
                description="",
                project_name="default",
                region="cn-beijing",
            )
        ],
        next_token=next_token,
    )


def _skill_space(space_id: str) -> SimpleNamespace:
    return SimpleNamespace(id=space_id, name=f"Team {space_id}", project_name="p")


def _skill_page(skill_id: str, total_count: int) -> SimpleNamespace:
    return SimpleNamespace(
        items=[
            SimpleNamespace(
                skill_id=skill_id,
                skill_name=skill_id,
                skill_description="",
                version="v1",
                skill_status="Published",
            )
        ],
        total_count=total_count,
    )


@pytest.mark.asyncio
async def test_knowledge_sweep_reports_partial_results_at_the_deadline(
    monkeypatch,
) -> None:
    clock = _CallClock()
    _use_clock(monkeypatch, knowledge_module, clock)
    requests = []

    class Client:
        def list_knowledge_bases(self, request):
            requests.append(request)
            # One page alone outlives the whole sweep budget.
            clock.set(_SOLO, _KNOWLEDGE_BUDGET + 1)
            return _knowledge_page(1, "next")

    source = AgentKitKnowledgeSource(
        client_factory=lambda credentials, region: Client(),
        credential_resolver=_credentials,
    )

    result = await asyncio.wait_for(source.collect(), _TIMEOUT)

    # The next page was promised by the token and abandoned by the deadline.
    assert len(requests) == 1
    assert [resource.descriptor.ref for resource in result.resources] == [
        "agentkit_kb:kb-1"
    ]
    assert result.status.status == "error"
    assert result.status.count == 1
    assert "collected so far" in result.status.message


@pytest.mark.asyncio
async def test_knowledge_slow_final_page_still_reports_deadline(monkeypatch) -> None:
    """A final page crossing the budget must not be labelled successful."""
    clock = _CallClock()
    _use_clock(monkeypatch, knowledge_module, clock)

    class Client:
        def list_knowledge_bases(self, request):
            clock.set(_SOLO, _KNOWLEDGE_BUDGET + 1)
            return _knowledge_page(1, "")

    source = AgentKitKnowledgeSource(
        client_factory=lambda credentials, region: Client(),
        credential_resolver=_credentials,
    )

    result = await asyncio.wait_for(source.collect(), _TIMEOUT)

    assert result.status.status == "error"
    assert result.status.count == 1


@pytest.mark.asyncio
async def test_concurrent_knowledge_sweeps_do_not_share_a_deadline(monkeypatch) -> None:
    """One instance, two sweeps: neither may answer for the other.

    The healthy sweep is parked mid-pagination while the breaching sweep runs
    start to finish, so a deadline latched on the instance is still set when
    the healthy sweep reads its own verdict.
    """
    clock = _CallClock()
    _use_clock(monkeypatch, knowledge_module, clock)
    gate = _Gate()

    class Client:
        def list_knowledge_bases(self, request):
            call = _CURRENT_CALL.get()
            first_page = not request.next_token
            if call == _CLEAN and first_page:
                # Hold the healthy sweep open across the breaching one.
                gate.enter()
            if call == _BREACHING:
                clock.set(_BREACHING, _KNOWLEDGE_BUDGET + 1)
            return _knowledge_page(1, "next") if first_page else _knowledge_page(2, "")

    source = AgentKitKnowledgeSource(
        client_factory=lambda credentials, region: Client(),
        credential_resolver=_credentials,
    )

    clean_task = asyncio.create_task(_collect_as(_CLEAN, source))
    try:
        await gate.wait_entered()
        breaching = await asyncio.wait_for(_collect_as(_BREACHING, source), _TIMEOUT)
    finally:
        gate.release()
    clean = await asyncio.wait_for(clean_task, _TIMEOUT)

    assert breaching.status.status == "error"
    assert breaching.status.count == 1
    assert [resource.descriptor.ref for resource in breaching.resources] == [
        "agentkit_kb:kb-1"
    ]

    assert clean.status.status == "ok"
    assert clean.status.count == 2
    assert clean.status.message is None
    assert [resource.descriptor.ref for resource in clean.resources] == [
        "agentkit_kb:kb-1",
        "agentkit_kb:kb-2",
    ]


@pytest.mark.asyncio
async def test_skill_sweep_reports_partial_results_at_the_deadline(monkeypatch) -> None:
    clock = _CallClock()
    _use_clock(monkeypatch, skills_module, clock)
    skill_requests = []

    class Client:
        def list_skill_spaces(self, request):
            return SimpleNamespace(items=[_skill_space("ss-one")], total_count=1)

        def list_skills_by_skill_space(self, request):
            skill_requests.append(request)
            clock.set(_SOLO, _SKILLS_BUDGET + 1)
            return _skill_page("skill-a", total_count=2)

    source = AgentKitSkillCenterSource(
        client_factory=lambda credentials, region: Client(),
        credential_resolver=_credentials,
    )

    result = await asyncio.wait_for(source.collect(), _TIMEOUT)

    assert [request.page_number for request in skill_requests] == [1]
    assert [resource.descriptor.ref for resource in result.resources] == [
        "ss-one:skill-a"
    ]
    assert result.status.status == "error"
    assert result.status.count == 1
    # The deadline `break` skips the `for...else` page-limit `raise`.
    assert "gave up after" in result.status.message
    assert "exceeded 100 pages" not in result.status.message


@pytest.mark.asyncio
async def test_skill_slow_final_page_still_reports_deadline(monkeypatch) -> None:
    """A complete-looking final Skill page still honours the elapsed budget."""
    clock = _CallClock()
    _use_clock(monkeypatch, skills_module, clock)

    class Client:
        def list_skill_spaces(self, request):
            return SimpleNamespace(items=[_skill_space("ss-one")], total_count=1)

        def list_skills_by_skill_space(self, request):
            clock.set(_SOLO, _SKILLS_BUDGET + 1)
            return _skill_page("skill-a", total_count=1)

    source = AgentKitSkillCenterSource(
        client_factory=lambda credentials, region: Client(),
        credential_resolver=_credentials,
    )

    result = await asyncio.wait_for(source.collect(), _TIMEOUT)

    assert result.status.status == "error"
    assert result.status.count == 1


@pytest.mark.asyncio
async def test_skill_space_sweep_deadline_skips_the_page_limit_error(
    monkeypatch,
) -> None:
    clock = _CallClock()
    _use_clock(monkeypatch, skills_module, clock)
    space_requests = []

    class Client:
        def list_skill_spaces(self, request):
            space_requests.append(request)
            clock.set(_SOLO, _SKILLS_BUDGET + 1)
            # `total_count` promises a second page the deadline never fetches.
            return SimpleNamespace(items=[_skill_space("ss-one")], total_count=2)

        def list_skills_by_skill_space(self, request):
            raise AssertionError("a breached sweep must not keep paginating")

    clients_created = 0

    def client_factory(credentials, region):
        nonlocal clients_created
        clients_created += 1
        return Client()

    source = AgentKitSkillCenterSource(
        client_factory=client_factory,
        credential_resolver=_credentials,
    )

    result = await asyncio.wait_for(source.collect(), _TIMEOUT)

    assert [request.page_number for request in space_requests] == [1]
    assert result.resources == []
    assert result.status.status == "error"
    assert result.status.count == 0
    assert clients_created == 1
    assert "gave up after" in result.status.message
    assert "exceeded 100 pages" not in result.status.message


@pytest.mark.asyncio
async def test_concurrent_skill_sweeps_do_not_share_a_deadline(monkeypatch) -> None:
    """Same instance, overlapping sweeps: one breach must not taint the other."""
    clock = _CallClock()
    _use_clock(monkeypatch, skills_module, clock)
    gate = _Gate()

    class Client:
        def list_skill_spaces(self, request):
            if _CURRENT_CALL.get() == _CLEAN:
                # Hold the healthy sweep open across the breaching one.
                gate.enter()
            return SimpleNamespace(items=[_skill_space("ss-one")], total_count=1)

        def list_skills_by_skill_space(self, request):
            if request.page_number == 1:
                if _CURRENT_CALL.get() == _BREACHING:
                    clock.set(_BREACHING, _SKILLS_BUDGET + 1)
                return _skill_page("skill-a", total_count=2)
            return _skill_page("skill-b", total_count=2)

    source = AgentKitSkillCenterSource(
        client_factory=lambda credentials, region: Client(),
        credential_resolver=_credentials,
    )

    clean_task = asyncio.create_task(_collect_as(_CLEAN, source))
    try:
        await gate.wait_entered()
        breaching = await asyncio.wait_for(_collect_as(_BREACHING, source), _TIMEOUT)
    finally:
        gate.release()
    clean = await asyncio.wait_for(clean_task, _TIMEOUT)

    assert breaching.status.status == "error"
    assert breaching.status.count == 1
    assert [resource.descriptor.ref for resource in breaching.resources] == [
        "ss-one:skill-a"
    ]

    assert clean.status.status == "ok"
    assert clean.status.count == 2
    assert clean.status.message is None
    assert [resource.descriptor.ref for resource in clean.resources] == [
        "ss-one:skill-a",
        "ss-one:skill-b",
    ]
