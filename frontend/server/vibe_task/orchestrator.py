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

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from veadk.cli.codex_app_server import CodexAppServerEvent

from .models import TaskStage, TaskState
from .runner import (
    CommandResult,
    CompletionGates,
    ValidationStep,
    build_context_prompt,
    invoke_succeeded,
    logs_have_blockers,
    may_start_cloud_attempt,
    redacted_evidence,
    runtime_is_ready,
    validation_policy,
)
from .runtime_manager import VibeTaskRuntimeManager
from .sandbox import VibeSandboxStore


@dataclass(frozen=True)
class OrchestratorTransition:
    event_type: str
    stage: TaskStage
    payload: dict[str, object] = field(default_factory=dict)
    projection: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class OrchestrationResult:
    state: TaskState
    gates: CompletionGates
    cloud_attempts: int
    reason: str = ""


TransitionCallback = Callable[[str, str, OrchestratorTransition], Awaitable[None]]
ExecutorCallback = Callable[
    [str, str, tuple[str, ...], str, int], Awaitable[CommandResult]
]
ArtifactCallback = Callable[[str, str], Awaitable[bool]]
Clock = Callable[[], datetime]


class VibeTaskOrchestrator:
    """Drive one Vibe task through Codex and independently verified gates."""

    def __init__(
        self,
        runtimes: VibeTaskRuntimeManager,
        store: VibeSandboxStore,
        transition: TransitionCallback,
        executor: ExecutorCallback,
        artifact: ArtifactCallback,
        *,
        project_root: str = "/home/gem/workspace",
        clock: Clock | None = None,
    ) -> None:
        self._runtimes = runtimes
        self._store = store
        self._transition = transition
        self._executor = executor
        self._artifact = artifact
        self._project_root = project_root
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._tasks: dict[tuple[str, str], asyncio.Task[OrchestrationResult]] = {}
        self._lock = asyncio.Lock()
        self._closing = False

    async def start(self, owner_id: str, task_id: str) -> OrchestrationResult:
        """Start or join the isolated orchestration for an owner/task pair."""
        key = (owner_id, task_id)
        async with self._lock:
            if self._closing:
                raise RuntimeError("orchestrator is closing")
            task = self._tasks.get(key)
            if task is None:
                task = asyncio.create_task(self._run(owner_id, task_id))
                self._tasks[key] = task
        try:
            return await asyncio.shield(task)
        finally:
            if task.done():
                async with self._lock:
                    if self._tasks.get(key) is task:
                        self._tasks.pop(key, None)

    async def cancel(self, owner_id: str, task_id: str) -> None:
        key = (owner_id, task_id)
        async with self._lock:
            task = self._tasks.get(key)
        if task is None:
            return
        await self._runtimes.interrupt(owner_id, task_id)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def close(self) -> None:
        async with self._lock:
            self._closing = True
            tasks = tuple(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self._runtimes.close_all()

    async def _run(self, owner_id: str, task_id: str) -> OrchestrationResult:
        await self._runtimes.connect(owner_id, task_id)
        try:
            status = await self._store.get(owner_id, task_id)
            if status.terminal:
                raise RuntimeError("cannot orchestrate a terminal task")
            intent = await self._store.get_intent(owner_id, task_id)
            prompt = "$veadk-agent-development " + build_context_prompt(
                goal=status.goal,
                summary=intent.model_dump(by_alias=True),
                versions={},
                evidence=intent.evidence,
                attempt=status.attempt,
                expires_at=status.expires_at,
            )
            await self._emit(
                owner_id,
                task_id,
                "task.started",
                TaskStage.UNDERSTANDING,
                projection={
                    "state": TaskState.RUNNING,
                    "stage": TaskStage.UNDERSTANDING,
                },
            )
            await self._codex_turn(owner_id, task_id, prompt)

            policy = validation_policy(
                runtime_name=task_id,
                project_root=f"{self._project_root.rstrip('/')}/{task_id}",
            )
            local_ok = await self._run_local(owner_id, task_id, policy.local_steps)
            if not local_ok:
                return await self._finish(
                    owner_id,
                    task_id,
                    CompletionGates(False, False, False, False, False, False),
                    status.attempt,
                    "local validation failed",
                )

            expires_at = datetime.fromisoformat(
                status.expires_at.replace("Z", "+00:00")
            )
            attempts = status.attempt
            cloud_results: dict[str, bool] = {}
            reason = ""
            while True:
                decision = may_start_cloud_attempt(
                    attempt=attempts,
                    now=self._clock(),
                    expires_at=expires_at,
                )
                if not decision.allowed:
                    reason = decision.reason
                    break
                attempts += 1
                await self._emit(
                    owner_id,
                    task_id,
                    "validation.cloud.started",
                    TaskStage.CLOUD_BUILD,
                    payload={"attempt": attempts},
                    projection={"attempt": attempts, "stage": TaskStage.CLOUD_BUILD},
                )
                cloud_results = await self._run_cloud(
                    owner_id, task_id, policy.cloud_steps
                )
                if cloud_results and all(cloud_results.values()):
                    break
                await self._codex_turn(
                    owner_id,
                    task_id,
                    "$veadk-agent-development Repair the project using the latest "
                    "independently verified validation evidence. Do not claim success; "
                    "the orchestrator will rerun every required gate.",
                )

            artifact_ready = False
            if cloud_results and all(cloud_results.values()):
                artifact_ready = bool(await self._artifact(owner_id, task_id))
            gates = CompletionGates(
                local_ok=True,
                build_ok=all(
                    cloud_results.get(name, False)
                    for name in ("deploy-config", "deploy-build", "deploy-apply")
                ),
                runtime_ready=cloud_results.get("runtime-ready", False),
                invoke_ok=cloud_results.get("invoke", False),
                logs_checked=cloud_results.get("logs", False),
                artifact_ready=artifact_ready,
            )
            return await self._finish(owner_id, task_id, gates, attempts, reason)
        except asyncio.CancelledError:
            await self._emit(
                owner_id,
                task_id,
                "task.cancelled",
                TaskStage.DONE,
                projection={"state": TaskState.CANCELLED, "stage": TaskStage.DONE},
            )
            raise
        except Exception as error:
            await self._emit(
                owner_id,
                task_id,
                "task.failed",
                TaskStage.DONE,
                payload={"errorType": type(error).__name__},
                projection={
                    "state": TaskState.FAILED,
                    "stage": TaskStage.DONE,
                    "error": "Vibe Task execution failed",
                },
            )
            raise
        finally:
            await self._runtimes.close(owner_id, task_id)

    async def _run_local(
        self,
        owner_id: str,
        task_id: str,
        steps: tuple[ValidationStep, ...],
    ) -> bool:
        for repair in range(2):
            results = await self._run_steps(owner_id, task_id, steps)
            if all(results.values()):
                return True
            if repair == 0:
                await self._codex_turn(
                    owner_id,
                    task_id,
                    "$veadk-agent-development Repair the local validation failure "
                    "shown in the durable evidence. Do not run cloud commands.",
                )
        return False

    async def _run_cloud(
        self,
        owner_id: str,
        task_id: str,
        steps: tuple[ValidationStep, ...],
    ) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for step in steps:
            result = await self._execute(owner_id, task_id, step)
            if step.name == "runtime-ready":
                passed = runtime_is_ready(result)
            elif step.name == "invoke":
                passed = invoke_succeeded(result)
            elif step.name == "logs":
                passed = not logs_have_blockers(result)
            else:
                passed = result.succeeded
            results[step.name] = passed
            if not passed:
                break
        return results

    async def _run_steps(
        self,
        owner_id: str,
        task_id: str,
        steps: tuple[ValidationStep, ...],
    ) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for step in steps:
            result = await self._execute(owner_id, task_id, step)
            results[step.name] = result.succeeded
            if not result.succeeded:
                break
        return results

    async def _execute(
        self, owner_id: str, task_id: str, step: ValidationStep
    ) -> CommandResult:
        result = await self._executor(
            owner_id,
            task_id,
            step.argv,
            self._project_root,
            step.timeout,
        )
        await self._emit(
            owner_id,
            task_id,
            "validation.step.finished",
            TaskStage.LOCAL_VALIDATION
            if step.stage == "local"
            else TaskStage.RUNTIME_VALIDATION,
            payload={
                "name": step.name,
                "stage": step.stage,
                "evidence": redacted_evidence(result),
            },
        )
        return result

    async def _codex_turn(self, owner_id: str, task_id: str, prompt: str) -> None:
        async for event in self._runtimes.run(owner_id, task_id, prompt):
            await self._transition(owner_id, task_id, self.map_codex_event(event))

    @staticmethod
    def map_codex_event(event: CodexAppServerEvent) -> OrchestratorTransition:
        # Arguments and responses can contain credentials or raw tool output. They are
        # deliberately excluded; only display fields pass through the redaction helper.
        safe = redacted_evidence(
            CommandResult(0, stdout=event.text, stderr=event.name), limit=8_000
        )
        payload: dict[str, object] = {
            "kind": event.kind,
            "status": event.status,
        }
        if safe["stdout"]:
            payload["text"] = safe["stdout"]
        if safe["stderr"]:
            payload["name"] = safe["stderr"]
        return OrchestratorTransition(
            "codex.event", TaskStage.BUILDING, payload=payload
        )

    async def _finish(
        self,
        owner_id: str,
        task_id: str,
        gates: CompletionGates,
        attempts: int,
        reason: str,
    ) -> OrchestrationResult:
        completed = gates.completed
        state = TaskState.COMPLETED if completed else TaskState.FAILED
        await self._emit(
            owner_id,
            task_id,
            "task.completed" if completed else "task.failed",
            TaskStage.DONE,
            payload={
                "gates": {
                    "localOk": gates.local_ok,
                    "buildOk": gates.build_ok,
                    "runtimeReady": gates.runtime_ready,
                    "invokeOk": gates.invoke_ok,
                    "logsChecked": gates.logs_checked,
                    "artifactReady": gates.artifact_ready,
                },
                **({"reason": reason} if reason else {}),
            },
            projection={"state": state, "stage": TaskStage.DONE, "attempt": attempts},
        )
        return OrchestrationResult(state, gates, attempts, reason)

    async def _emit(
        self,
        owner_id: str,
        task_id: str,
        event_type: str,
        stage: TaskStage,
        *,
        payload: dict[str, object] | None = None,
        projection: dict[str, object] | None = None,
    ) -> None:
        await self._transition(
            owner_id,
            task_id,
            OrchestratorTransition(
                event_type,
                stage,
                payload or {},
                projection or {},
            ),
        )
