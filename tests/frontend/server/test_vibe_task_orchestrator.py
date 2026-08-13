from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import pytest

from frontend.server.vibe_task.models import (
    IntentSummary,
    TaskStage,
    TaskState,
    TaskStatus,
)
from frontend.server.vibe_task.orchestrator import (
    OrchestratorTransition,
    VibeTaskOrchestrator,
)
from frontend.server.vibe_task.runner import CommandResult
from veadk.cli.codex_app_server import CodexAppServerEvent


class FakeRuntimes:
    def __init__(self, events: list[CodexAppServerEvent] | None = None) -> None:
        self.events = events or [CodexAppServerEvent(kind="text", text="working")]
        self.prompts: list[str] = []
        self.connected: list[tuple[str, str]] = []
        self.closed: list[tuple[str, str]] = []
        self.interrupted: list[tuple[str, str]] = []
        self.closed_all = False

    async def connect(self, owner_id: str, task_id: str) -> object:
        self.connected.append((owner_id, task_id))
        return object()

    async def run(
        self, owner_id: str, task_id: str, prompt: str
    ) -> AsyncIterator[CodexAppServerEvent]:
        del owner_id, task_id
        self.prompts.append(prompt)
        for event in self.events:
            yield event

    async def interrupt(self, owner_id: str, task_id: str) -> None:
        self.interrupted.append((owner_id, task_id))

    async def close(self, owner_id: str, task_id: str) -> None:
        self.closed.append((owner_id, task_id))

    async def close_all(self) -> None:
        self.closed_all = True


class FakeStore:
    def __init__(
        self, *, attempt: int = 0, expires_in: timedelta = timedelta(hours=2)
    ) -> None:
        now = datetime.now(timezone.utc)
        self.status = TaskStatus(
            task_id="runtime-1",
            display_name="task",
            goal="build an agent",
            state=TaskState.READY,
            stage=TaskStage.UNDERSTANDING,
            created_at=now.isoformat(),
            expires_at=(now + expires_in).isoformat(),
            attempt=attempt,
        )
        self.intent = IntentSummary(revision=1, goal=self.status.goal)

    async def get(self, owner_id: str, task_id: str) -> TaskStatus:
        del owner_id, task_id
        return self.status

    async def get_intent(self, owner_id: str, task_id: str) -> IntentSummary:
        del owner_id, task_id
        return self.intent


class Harness:
    def __init__(
        self,
        results: dict[str, list[CommandResult]],
        *,
        artifact: bool = True,
        store: FakeStore | None = None,
        codex_events: list[CodexAppServerEvent] | None = None,
    ) -> None:
        self.runtimes = FakeRuntimes(codex_events)
        self.store = store or FakeStore()
        self.transitions: list[OrchestratorTransition] = []
        self.calls: list[tuple[str, ...]] = []
        self.artifact_calls = 0
        self._results = {name: list(values) for name, values in results.items()}
        self._artifact = artifact
        self.orchestrator = VibeTaskOrchestrator(
            self.runtimes,  # type: ignore[arg-type]
            self.store,  # type: ignore[arg-type]
            self.record,
            self.execute,
            self.make_artifact,
        )

    async def record(
        self, owner_id: str, task_id: str, transition: OrchestratorTransition
    ) -> None:
        del owner_id, task_id
        self.transitions.append(transition)

    async def execute(
        self,
        owner_id: str,
        task_id: str,
        argv: tuple[str, ...],
        cwd: str,
        timeout: int,
    ) -> CommandResult:
        del owner_id, task_id, cwd, timeout
        self.calls.append(argv)
        name = next(name for name in self._results if argv == command_for(name))
        values = self._results[name]
        return values.pop(0) if len(values) > 1 else values[0]

    async def make_artifact(self, owner_id: str, task_id: str) -> bool:
        del owner_id, task_id
        self.artifact_calls += 1
        return self._artifact


def command_for(name: str) -> tuple[str, ...]:
    commands = {
        "compile": ("python", "-m", "compileall", "-q", "."),
        "deploy-config": ("ak", "config", "--runtime_name", "runtime-1"),
        "deploy-build": ("ak", "build"),
        "deploy-apply": ("ak", "deploy"),
        "runtime-ready": ("ak", "runtime", "show", "runtime-1", "--json"),
        "invoke": (
            "ak",
            "invoke",
            "run",
            "VIBE_VALIDATION_SMOKE",
            "--config-file",
            "agentkit.yaml",
            "--raw",
        ),
        "logs": ("ak", "runtime", "logs", "runtime-1", "--limit", "200", "--json"),
    }
    return commands[name]


def success_results() -> dict[str, list[CommandResult]]:
    return {
        "compile": [CommandResult(0)],
        "deploy-config": [CommandResult(0)],
        "deploy-build": [CommandResult(0)],
        "deploy-apply": [CommandResult(0)],
        "runtime-ready": [CommandResult(0, '{"status":"Ready"}')],
        "invoke": [CommandResult(0, '{"success":true}')],
        "logs": [CommandResult(0, "request completed")],
    }


@pytest.mark.asyncio
async def test_happy_path_builds_prefixed_context_and_completes() -> None:
    harness = Harness(success_results())

    result = await harness.orchestrator.start("owner", "runtime-1")

    assert result.state is TaskState.COMPLETED
    assert result.gates.completed
    assert harness.runtimes.prompts[0].startswith(
        "$veadk-agent-development Use Context over Control."
    )
    assert '"goal": "build an agent"' in harness.runtimes.prompts[0]
    assert harness.artifact_calls == 1
    assert harness.transitions[-1].event_type == "task.completed"


@pytest.mark.asyncio
async def test_local_failure_gets_one_repair_then_fails_without_cloud() -> None:
    results = success_results()
    results["compile"] = [CommandResult(1, stderr="syntax error"), CommandResult(1)]
    harness = Harness(results)

    result = await harness.orchestrator.start("owner", "runtime-1")

    assert result.state is TaskState.FAILED
    assert harness.calls == [command_for("compile"), command_for("compile")]
    assert len(harness.runtimes.prompts) == 2
    assert "Repair the local validation failure" in harness.runtimes.prompts[1]
    assert harness.artifact_calls == 0


@pytest.mark.asyncio
async def test_cloud_attempts_are_capped_at_three() -> None:
    results = success_results()
    results["deploy-build"] = [CommandResult(1)]
    harness = Harness(results)

    result = await harness.orchestrator.start("owner", "runtime-1")

    assert result.state is TaskState.FAILED
    assert result.cloud_attempts == 3
    assert result.reason == "cloud attempt limit reached"
    assert harness.calls.count(command_for("deploy-build")) == 3
    assert harness.artifact_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "result"),
    [
        ("deploy-build", CommandResult(1)),
        ("runtime-ready", CommandResult(0, '{"status":"Pending"}')),
        ("invoke", CommandResult(0, '{"success":false}')),
        ("logs", CommandResult(0, "Traceback: failure")),
    ],
)
async def test_completion_requires_each_verified_command_gate(
    name: str, result: CommandResult
) -> None:
    results = success_results()
    results[name] = [result]
    harness = Harness(results, store=FakeStore(attempt=2))

    outcome = await harness.orchestrator.start("owner", "runtime-1")

    assert outcome.state is TaskState.FAILED
    assert not outcome.gates.completed
    assert harness.transitions[-1].event_type == "task.failed"


@pytest.mark.asyncio
async def test_completion_requires_artifact_callback_success() -> None:
    harness = Harness(success_results(), artifact=False)

    result = await harness.orchestrator.start("owner", "runtime-1")

    assert result.state is TaskState.FAILED
    assert result.gates.artifact_ready is False
    assert harness.artifact_calls == 1


@pytest.mark.asyncio
async def test_time_guard_prevents_cloud_and_artifact() -> None:
    harness = Harness(
        success_results(), store=FakeStore(expires_in=timedelta(minutes=29))
    )

    result = await harness.orchestrator.start("owner", "runtime-1")

    assert result.state is TaskState.FAILED
    assert result.cloud_attempts == 0
    assert result.reason == "less than 30 minutes remain"
    assert harness.calls == [command_for("compile")]
    assert harness.artifact_calls == 0


@pytest.mark.asyncio
async def test_cancel_interrupts_and_closes_active_runtime() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    harness = Harness(success_results())

    async def blocked_run(
        owner_id: str, task_id: str, prompt: str
    ) -> AsyncIterator[CodexAppServerEvent]:
        del owner_id, task_id
        harness.runtimes.prompts.append(prompt)
        started.set()
        await release.wait()
        yield CodexAppServerEvent(kind="text", text="unused")

    harness.runtimes.run = blocked_run  # type: ignore[method-assign]
    running = asyncio.create_task(harness.orchestrator.start("owner", "runtime-1"))
    await started.wait()

    await harness.orchestrator.cancel("owner", "runtime-1")

    with pytest.raises(asyncio.CancelledError):
        await running
    assert harness.runtimes.interrupted == [("owner", "runtime-1")]
    assert harness.runtimes.closed == [("owner", "runtime-1")]
    assert any(item.event_type == "task.cancelled" for item in harness.transitions)


@pytest.mark.asyncio
async def test_codex_event_mapping_excludes_raw_values_and_redacts_display_text() -> (
    None
):
    secret = "actual-secret"
    harness = Harness(
        success_results(),
        codex_events=[
            CodexAppServerEvent(
                kind="tool",
                text=f"API_TOKEN={secret}",
                name="Bearer bearer-token",
                arguments={"secret": secret},
                response={"token": secret},
            )
        ],
    )

    await harness.orchestrator.start("owner", "runtime-1")

    event = next(
        item for item in harness.transitions if item.event_type == "codex.event"
    )
    serialized = repr(event.payload)
    assert secret not in serialized
    assert "bearer-token" not in serialized
    assert "arguments" not in event.payload
    assert "response" not in event.payload
    assert "<redacted>" in serialized
