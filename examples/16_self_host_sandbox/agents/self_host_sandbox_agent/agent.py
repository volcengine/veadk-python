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
import logging
import sys
import threading
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

EXAMPLE_DIR = Path(__file__).resolve().parents[2]
if str(EXAMPLE_DIR) not in sys.path:
    sys.path.insert(0, str(EXAMPLE_DIR))
load_dotenv(EXAMPLE_DIR / ".env", override=False)

from sandbox_client import SelfHostSandboxClient  # noqa: E402
from veadk import Agent  # noqa: E402
from veadk.memory.short_term_memory import ShortTermMemory  # noqa: E402
from veadk.runtime import DispatchRuntimeProvider, ToolCall  # noqa: E402

logger = logging.getLogger("veadk.sandbox_agent")


class SandboxSessionManager:
    """Bind exactly one remote Managed Session to each VeADK session."""

    def __init__(self) -> None:
        self._clients: dict[str, SelfHostSandboxClient] = {}
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

    def release(self, veadk_session_id: str) -> None:
        key = veadk_session_id or "__default__"
        with self._lock:
            client = self._clients.pop(key, None)
        if client:
            client.post_status_idle()


sandbox_sessions = SandboxSessionManager()
sandbox_client = sandbox_sessions.get("__default__")


def bash(command: str, timeout: float = 120) -> dict:
    """Execute a shell command in the remote sandbox."""
    raise RuntimeError("Remote tools must be intercepted by DispatchRuntimeProvider")


def read_file(
    file_path: str, offset: int | None = None, limit: int | None = None
) -> dict:
    """Read a text file in the remote sandbox."""
    raise RuntimeError("Remote tools must be intercepted by DispatchRuntimeProvider")


def write_file(file_path: str, content: str) -> dict:
    """Create or overwrite a text file in the remote sandbox."""
    raise RuntimeError("Remote tools must be intercepted by DispatchRuntimeProvider")


def edit_file(
    file_path: str, old_string: str, new_string: str, replace_all: bool = False
) -> dict:
    """Replace an exact string in a remote sandbox file."""
    raise RuntimeError("Remote tools must be intercepted by DispatchRuntimeProvider")


def list_files(path: str = "/workspace", max_depth: int = 4) -> dict:
    """List files below a directory in the remote sandbox."""
    raise RuntimeError("Remote tools must be intercepted by DispatchRuntimeProvider")


def search_files(
    pattern: str,
    path: str = "/workspace",
    glob: str | None = None,
    case_insensitive: bool = False,
) -> dict:
    """Search files in the remote sandbox."""
    raise RuntimeError("Remote tools must be intercepted by DispatchRuntimeProvider")


def python(code: str, workdir: str = "/workspace", timeout: float = 120) -> dict:
    """Run Python code in the remote sandbox."""
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
short_term_memory = ShortTermMemory(after_create_session_callback=after_create_session)

# veadk web calls the service directly, so preserve the per-session callback
# when the UI creates a session outside Runner.create_session().
_create_local_session = short_term_memory.session_service.create_session


async def _create_session_with_remote(*args: Any, **kwargs: Any) -> Any:
    session = await _create_local_session(*args, **kwargs)
    if session is not None:
        await after_create_session(session)
    return session


short_term_memory.session_service.create_session = _create_session_with_remote

agent = Agent(
    name="self_host_sandbox_agent",
    description="An engineering agent dispatching tool calls to a Self-Hosted Worker.",
    instruction=(
        f"You are an autonomous engineering assistant connected to Runtime 7hw8g3yr "
        f"(Environment: {sandbox_client.environment_id}). Handle user conversation and "
        "model reasoning in VeADK. Use the provided tools for every sandbox operation; "
        "tool calls are dispatched through Runtime 7hw8g3yr to TAE Sandbox m3m24zxs."
    ),
    tools=[bash, read_file, write_file, edit_file, list_files, search_files, python],
    short_term_memory=short_term_memory,
    before_tool_callback=dispatch_runtime.before_tool_callback,
)

root_agent = agent
