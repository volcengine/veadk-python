from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from frontend.server.vibe_task.runtime_manager import (
    VibeRuntimeError,
    VibeTaskRuntimeManager,
)
from veadk.cli.codex_app_server import CodexAppServerEvent, CodexSkill
from veadk.cli.frontend_sandbox import SandboxCloudSession


class FakeCodex:
    def __init__(
        self,
        calls: list[str],
        *,
        skills: tuple[CodexSkill, ...] | None = None,
    ) -> None:
        self.calls = calls
        self.skills = skills or (
            CodexSkill(
                id="development-skill-id",
                name="veadk-agent-development",
            ),
        )
        self.active = False
        self.closed = False
        self.interrupts = 0
        self.turn_prompts: list[tuple[str, tuple[str, ...]]] = []
        self.turn_started = asyncio.Event()
        self.release_turn = asyncio.Event()

    async def update_workspace(self, cwd: str) -> str:
        self.calls.append(f"update:{cwd}")
        return cwd

    async def list_skills(self, force_reload: bool = False) -> tuple[CodexSkill, ...]:
        self.calls.append(f"skills:{force_reload}")
        return self.skills

    async def stream_turn(
        self, prompt: str, skill_ids: tuple[str, ...] = ()
    ) -> AsyncIterator[CodexAppServerEvent]:
        self.active = True
        self.turn_prompts.append((prompt, skill_ids))
        self.turn_started.set()
        try:
            await self.release_turn.wait()
            yield CodexAppServerEvent(kind="text", text=prompt)
        finally:
            self.active = False

    async def interrupt(self) -> None:
        self.interrupts += 1
        self.release_turn.set()

    async def close(self) -> None:
        self.calls.append("close")
        self.closed = True
        self.release_turn.set()


class FakeGateway:
    def __init__(self, factory=None) -> None:
        self.factory = factory or (lambda calls: FakeCodex(calls))
        self.calls: list[str] = []
        self.connections: list[FakeCodex] = []
        self.deleted: list[SandboxCloudSession] = []

    async def open_codex(self, session: SandboxCloudSession) -> FakeCodex:
        self.calls.append(f"open:{session.instance_id}")
        connection = self.factory(self.calls)
        self.connections.append(connection)
        return connection

    async def delete_session(self, session: SandboxCloudSession) -> None:
        self.deleted.append(session)


def cloud(task_id: str = "task-1") -> SandboxCloudSession:
    return SandboxCloudSession(
        tool_id="dev-tool",
        instance_id="sandbox-1",
        user_session_id=task_id,
        endpoint="https://sandbox.example",
        status="Ready",
        created_by="owner-1",
    )


def manager(gateway: FakeGateway, resolver=None, ensure_workspace=None):
    async def default_resolver(owner_id: str, task_id: str) -> SandboxCloudSession:
        del owner_id
        return cloud(task_id)

    async def default_workspace(session: SandboxCloudSession) -> str:
        gateway.calls.append(f"ensure:{session.instance_id}")
        return "/home/gem/workspace"

    return VibeTaskRuntimeManager(
        gateway,
        resolver or default_resolver,
        ensure_workspace or default_workspace,
    )


@pytest.mark.asyncio
async def test_connect_uses_ownership_resolver() -> None:
    gateway = FakeGateway()
    resolved: list[tuple[str, str]] = []

    async def resolve(owner_id: str, task_id: str) -> SandboxCloudSession:
        resolved.append((owner_id, task_id))
        if owner_id != "owner-1":
            raise PermissionError("not owned")
        return cloud(task_id)

    runtimes = manager(gateway, resolver=resolve)
    await runtimes.connect("owner-1", "task-1")

    assert resolved == [("owner-1", "task-1")]
    with pytest.raises(PermissionError, match="not owned"):
        await runtimes.connect("owner-2", "task-1")
    assert len(gateway.connections) == 1


@pytest.mark.asyncio
async def test_duplicate_connect_race_closes_loser() -> None:
    gateway = FakeGateway()
    both_open = asyncio.Event()
    release_open = asyncio.Event()

    async def open_codex(session: SandboxCloudSession) -> FakeCodex:
        connection = FakeCodex(gateway.calls)
        gateway.connections.append(connection)
        if len(gateway.connections) == 2:
            both_open.set()
        await release_open.wait()
        return connection

    gateway.open_codex = open_codex
    runtimes = manager(gateway)
    first = asyncio.create_task(runtimes.connect("owner-1", "task-1"))
    second = asyncio.create_task(runtimes.connect("owner-1", "task-1"))
    await both_open.wait()
    release_open.set()

    first_runtime, second_runtime = await asyncio.gather(first, second)

    assert first_runtime is second_runtime
    assert len(gateway.connections) == 2
    assert sum(connection.closed for connection in gateway.connections) == 1


@pytest.mark.asyncio
async def test_connect_ensures_workspace_before_open_and_update() -> None:
    gateway = FakeGateway()
    runtimes = manager(gateway)

    await runtimes.connect("owner-1", "task-1")

    assert gateway.calls == [
        "ensure:sandbox-1",
        "open:sandbox-1",
        "update:/home/gem/workspace",
        "skills:True",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "skills",
    [
        (CodexSkill(id="other", name="other-skill"),),
        (
            CodexSkill(id="development-1", name="veadk-agent-development"),
            CodexSkill(id="development-2", name="veadk-agent-development"),
        ),
    ],
    ids=["missing", "duplicate"],
)
async def test_connect_closes_without_exactly_one_development_skill(
    skills: tuple[CodexSkill, ...],
) -> None:
    gateway = FakeGateway(
        lambda calls: FakeCodex(
            calls,
            skills=skills,
        )
    )
    runtimes = manager(gateway)

    with pytest.raises(VibeRuntimeError) as error:
        await runtimes.connect("owner-1", "task-1")

    assert error.value.code == "VIBE_DEVELOPMENT_SKILL_INVALID"
    assert gateway.connections[0].closed is True


async def collect_turn(runtimes: VibeTaskRuntimeManager, prompt: str) -> list[str]:
    return [event.text async for event in runtimes.run("owner-1", "task-1", prompt)]


@pytest.mark.asyncio
async def test_run_serializes_turns_and_selects_development_skill() -> None:
    gateway = FakeGateway()
    runtimes = manager(gateway)
    runtime = await runtimes.connect("owner-1", "task-1")
    first = asyncio.create_task(
        collect_turn(runtimes, " $veadk-agent-development first ")
    )
    await runtime.codex.turn_started.wait()
    second = asyncio.create_task(
        collect_turn(runtimes, "$veadk-agent-development second")
    )
    await asyncio.sleep(0)

    assert len(runtime.codex.turn_prompts) == 1
    runtime.codex.release_turn.set()
    assert await first == ["$veadk-agent-development first"]
    assert await second == ["$veadk-agent-development second"]
    assert runtime.codex.turn_prompts == [
        ("$veadk-agent-development first", ("development-skill-id",)),
        ("$veadk-agent-development second", ("development-skill-id",)),
    ]
    for invalid_prompt in (
        "build an agent",
        "$veadk-agent-development-extra build",
    ):
        with pytest.raises(VibeRuntimeError) as error:
            await collect_turn(runtimes, invalid_prompt)
        assert error.value.code == "VIBE_DEVELOPMENT_SKILL_REQUIRED"


@pytest.mark.asyncio
async def test_interrupt_and_close_all_preserve_cloud_sessions() -> None:
    gateway = FakeGateway()
    runtimes = manager(gateway)
    first = await runtimes.connect("owner-1", "task-1")
    second = await runtimes.connect("owner-1", "task-2")

    turn = asyncio.create_task(
        collect_turn(runtimes, "$veadk-agent-development build")
    )
    await first.codex.turn_started.wait()
    await runtimes.interrupt("owner-1", "task-1")
    await turn
    second.codex.active = True

    await runtimes.close_all()

    assert first.codex.interrupts == 1
    assert second.codex.interrupts == 1
    assert first.codex.closed is True
    assert second.codex.closed is True
    assert gateway.deleted == []
    with pytest.raises(VibeRuntimeError):
        await runtimes.interrupt("owner-1", "task-1")
