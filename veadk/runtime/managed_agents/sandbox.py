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

"""VeADK agent whose tool calls run through a Self-Hosted Sandbox Runtime."""

import asyncio
import functools
import logging
import threading
from typing import Any

from functools import lru_cache
from veadk.integrations.mpa.session_client import SelfHostSandboxClient
from veadk import Agent
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.runtime import DispatchRuntimeProvider, ToolCall

logger = logging.getLogger("veadk.sandbox_agent")


class SandboxSessionManager:
    """Bind exactly one remote Managed Session to each VeADK session."""

    def __init__(self) -> None:
        self._clients: dict[str, SelfHostSandboxClient] = {}
        self._active_turns: dict[str, int] = {}
        self._lock = threading.Lock()

    def _new_client(self) -> SelfHostSandboxClient:
        client = SelfHostSandboxClient()
        client.session_id = None
        return client

    def get(self, veadk_session_id: str) -> SelfHostSandboxClient:
        key = veadk_session_id or "__default__"
        with self._lock:
            client = self._clients.get(key)
            if client is None:
                client = self._new_client()
                self._clients[key] = client
            return client

    def bind(self, veadk_session_id: str, client: SelfHostSandboxClient) -> None:
        key = veadk_session_id or "__default__"
        with self._lock:
            self._clients[key] = client

    def create_remote_session(self, veadk_session_id: str) -> str:
        client = self.get(veadk_session_id)
        if not client.session_id:
            client.create_session(
                title=f"VeADK Self-Hosted Sandbox Session {veadk_session_id}"
            )
        return client.session_id or ""

    def begin_turn(self, veadk_session_id: str) -> None:
        """Track a local turn without writing a synthetic Session event."""
        key = veadk_session_id or "__default__"
        client = self.get(key)
        if not client.session_id:
            self.create_remote_session(key)

        with self._lock:
            self._active_turns[key] = self._active_turns.get(key, 0) + 1

    def end_turn(self, veadk_session_id: str) -> None:
        """Mark the remote Session idle after the last overlapping local turn."""
        key = veadk_session_id or "__default__"
        with self._lock:
            active_turns = self._active_turns.get(key, 0)
            if active_turns <= 0:
                return
            if active_turns > 1:
                self._active_turns[key] = active_turns - 1
                return
            self._active_turns.pop(key, None)
            client = self._clients.get(key)
            if client:
                client.post_status_idle()

    def release(self, veadk_session_id: str) -> None:
        key = veadk_session_id or "__default__"
        with self._lock:
            client = self._clients.pop(key, None)
            self._active_turns.pop(key, None)
        if client:
            client.post_status_idle()


sandbox_sessions = SandboxSessionManager()


def enable_sandbox_turn_lifecycle(runner: Any) -> Any:
    """Wrap ``runner.run_async`` to mark the remote Session idle after a turn."""
    if getattr(runner, "_sandbox_turn_lifecycle_enabled", False):
        return runner

    original_run_async = runner.run_async

    @functools.wraps(original_run_async)
    async def run_async_with_sandbox_turn(*args: Any, **kwargs: Any):
        session_id = str(kwargs.get("session_id") or "")
        if not session_id:
            async for event in original_run_async(*args, **kwargs):
                yield event
            return

        await asyncio.to_thread(sandbox_sessions.begin_turn, session_id)
        try:
            async for event in original_run_async(*args, **kwargs):
                yield event
        finally:
            await asyncio.to_thread(sandbox_sessions.end_turn, session_id)

    runner.run_async = run_async_with_sandbox_turn
    runner._sandbox_turn_lifecycle_enabled = True
    return runner


def bash(
    command: str | None = None,
    restart: bool | None = None,
    timeout_ms: int | None = None,
) -> dict:
    """Execute a command or restart the persistent remote bash session."""
    raise RuntimeError("Remote tools must be intercepted by DispatchRuntimeProvider")


def read(file_path: str, view_range: list[int] | None = None) -> dict:
    """Read file contents, optionally selecting an inclusive line range."""
    raise RuntimeError("Remote tools must be intercepted by DispatchRuntimeProvider")


def write(file_path: str, content: str) -> dict:
    """Atomically write file contents in the remote sandbox."""
    raise RuntimeError("Remote tools must be intercepted by DispatchRuntimeProvider")


def edit(
    file_path: str, old_string: str, new_string: str, replace_all: bool = False
) -> dict:
    """Replace an exact string in a remote file."""
    raise RuntimeError("Remote tools must be intercepted by DispatchRuntimeProvider")


def glob(pattern: str, path: str | None = None) -> dict:
    """Find files matching a glob pattern."""
    raise RuntimeError("Remote tools must be intercepted by DispatchRuntimeProvider")


def grep(pattern: str, path: str | None = None) -> dict:
    """Search file contents using a regular expression."""
    raise RuntimeError("Remote tools must be intercepted by DispatchRuntimeProvider")


async def after_create_session(session: Any) -> None:
    veadk_session_id = str(getattr(session, "id", "") or "")
    remote_id = await asyncio.to_thread(
        sandbox_sessions.create_remote_session, veadk_session_id
    )
    logger.info(
        "Remote Managed Session created: veadk=%s remote=%s",
        veadk_session_id,
        remote_id,
    )


async def dispatch_task(tool_call: ToolCall) -> dict:
    client = sandbox_sessions.get(tool_call.session_id)
    return await asyncio.to_thread(
        client.dispatch_tool,
        tool_call.name,
        tool_call.arguments,
        dispatch_id=tool_call.id,
    )


dispatch_runtime = DispatchRuntimeProvider(dispatch_task, dispatchable_tools=None)


@lru_cache(maxsize=1)
def get_default_agent() -> Agent:
    """Build the optional demo Agent only when a caller explicitly requests it."""
    memory = ShortTermMemory(after_create_session_callback=after_create_session)
    return Agent(
        name="self_host_sandbox_agent",
        description="An engineering agent dispatching tools to a self-hosted Worker.",
        instruction=(
            "You are an engineering assistant. Handle conversation and model "
            "reasoning in VeADK and use the provided tools for sandbox operations."
        ),
        tools=[bash, read, write, edit, glob, grep],
        short_term_memory=memory,
        before_tool_callback=dispatch_runtime.before_tool_callback,
    )
