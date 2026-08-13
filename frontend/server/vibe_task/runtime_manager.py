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
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field

from veadk.cli.codex_app_server import CodexAppServerEvent
from veadk.cli.frontend_sandbox import (
    SandboxCloudGateway,
    SandboxCloudSession,
    SandboxCodexConnection,
)


_DEVELOPMENT_SKILL = "veadk-agent-development"
_DEVELOPMENT_PROMPT_PREFIX = f"${_DEVELOPMENT_SKILL}"

SandboxResolver = Callable[[str, str], Awaitable[SandboxCloudSession]]
WorkspaceEnsurer = Callable[[SandboxCloudSession], Awaitable[str]]


class VibeRuntimeError(RuntimeError):
    """A Vibe task cannot use its isolated Codex runtime."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class VibeTaskRuntime:
    """One local Codex connection for an owner/task pair."""

    cloud: SandboxCloudSession
    codex: SandboxCodexConnection
    skill_id: str
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    active_task: asyncio.Task[object] | None = None
    closing: bool = False


class VibeTaskRuntimeManager:
    """Manage isolated Codex runtimes without owning cloud Sessions."""

    def __init__(
        self,
        gateway: SandboxCloudGateway,
        resolver: SandboxResolver,
        ensure_workspace: WorkspaceEnsurer,
    ) -> None:
        self._gateway = gateway
        self._resolver = resolver
        self._ensure_workspace = ensure_workspace
        self._runtimes: dict[tuple[str, str], VibeTaskRuntime] = {}
        self._registry_lock = asyncio.Lock()
        self._closing = False

    async def connect(self, owner_id: str, task_id: str) -> VibeTaskRuntime:
        """Resolve and connect one task, deduplicating concurrent attempts."""
        key = (owner_id, task_id)
        if self._closing:
            raise VibeRuntimeError("VIBE_RUNTIME_CLOSING", "Runtime manager is closing")
        existing = self._runtimes.get(key)
        if existing is not None:
            return existing

        cloud = await self._resolver(owner_id, task_id)
        workspace = await self._ensure_workspace(cloud)
        codex = await self._gateway.open_codex(cloud)
        try:
            await codex.update_workspace(workspace)
            skills = await codex.list_skills(force_reload=True)
            matches = [skill for skill in skills if skill.name == _DEVELOPMENT_SKILL]
            if len(matches) != 1:
                raise VibeRuntimeError(
                    "VIBE_DEVELOPMENT_SKILL_INVALID",
                    "Dev Sandbox must expose exactly one enabled "
                    f"{_DEVELOPMENT_SKILL} skill",
                )
            runtime = VibeTaskRuntime(
                cloud=cloud,
                codex=codex,
                skill_id=matches[0].id,
            )
            async with self._registry_lock:
                if self._closing:
                    raise VibeRuntimeError(
                        "VIBE_RUNTIME_CLOSING", "Runtime manager is closing"
                    )
                existing = self._runtimes.get(key)
                if existing is None:
                    self._runtimes[key] = runtime
            if existing is not None:
                await codex.close()
                return existing
            return runtime
        except BaseException:
            await codex.close()
            raise

    def _owned(self, owner_id: str, task_id: str) -> VibeTaskRuntime:
        runtime = self._runtimes.get((owner_id, task_id))
        if runtime is None:
            raise VibeRuntimeError(
                "VIBE_RUNTIME_NOT_CONNECTED",
                "Vibe task runtime is not connected",
            )
        return runtime

    async def run(
        self, owner_id: str, task_id: str, prompt: str
    ) -> AsyncIterator[CodexAppServerEvent]:
        """Serialize turns and force use of the development skill."""
        normalized = prompt.strip()
        if not (
            normalized == _DEVELOPMENT_PROMPT_PREFIX
            or normalized.startswith(f"{_DEVELOPMENT_PROMPT_PREFIX} ")
        ):
            raise VibeRuntimeError(
                "VIBE_DEVELOPMENT_SKILL_REQUIRED",
                f"Prompt must begin with {_DEVELOPMENT_PROMPT_PREFIX}",
            )
        runtime = self._owned(owner_id, task_id)
        async with runtime.lock:
            if (
                runtime.closing
                or self._runtimes.get((owner_id, task_id)) is not runtime
            ):
                raise VibeRuntimeError(
                    "VIBE_RUNTIME_CLOSING", "Vibe task runtime is closing"
                )
            runtime.active_task = asyncio.current_task()
            try:
                async for event in runtime.codex.stream_turn(
                    normalized, (runtime.skill_id,)
                ):
                    yield event
            finally:
                runtime.active_task = None

    async def interrupt(self, owner_id: str, task_id: str) -> None:
        """Interrupt the active turn, if any."""
        await self._owned(owner_id, task_id).codex.interrupt()

    async def close(self, owner_id: str, task_id: str) -> None:
        """Close a local runtime without deleting its cloud Session."""
        key = (owner_id, task_id)
        async with self._registry_lock:
            runtime = self._runtimes.pop(key, None)
        if runtime is None:
            raise VibeRuntimeError(
                "VIBE_RUNTIME_NOT_CONNECTED",
                "Vibe task runtime is not connected",
            )
        runtime.closing = True
        active_task = runtime.active_task
        if active_task is not None and active_task is not asyncio.current_task():
            active_task.cancel()
            await runtime.codex.interrupt()
        async with runtime.lock:
            await runtime.codex.close()

    async def close_all(self) -> None:
        """Close all local runtimes while preserving their cloud Sessions."""
        async with self._registry_lock:
            self._closing = True
            runtimes = tuple(self._runtimes.values())
            self._runtimes.clear()

        async def close_runtime(runtime: VibeTaskRuntime) -> None:
            runtime.closing = True
            active_task = runtime.active_task
            if active_task is not None and active_task is not asyncio.current_task():
                active_task.cancel()
                await runtime.codex.interrupt()
            elif runtime.codex.active:
                await runtime.codex.interrupt()
            async with runtime.lock:
                await runtime.codex.close()

        if runtimes:
            await asyncio.gather(*(close_runtime(runtime) for runtime in runtimes))
