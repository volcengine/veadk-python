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

"""One Codex app-server turn that reports its result through a dynamic tool.

Studio drives every structured Codex turn the same way: dynamic tools registered on
``thread/start`` carry the result as typed JSON-RPC arguments, a rejected call returns
``success: false`` so the same turn can correct itself, and the turn ends as soon as the
contract has been delivered.  Callers own the contract: they pass the tool specs, the
validators, and the check that says the result has arrived.  A turn may register several
tools, because one analysis can both ask the user a question and report its result.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from veadk.cli.codex_app_server import (
    CodexAppServerError,
    CodexAppServerSession,
    CodexDynamicToolResult,
)

ToolHandler = Callable[
    [dict[str, object]],
    "CodexDynamicToolResult | Awaitable[CodexDynamicToolResult]",
]

__all__ = [
    "DynamicTool",
    "ToolHandler",
    "ToolTurnDeadlineExceeded",
    "ToolTurnUnavailable",
    "run_tool_turn",
]


class ToolTurnUnavailable(RuntimeError):
    """The Sandbox app-server could not start or finish the tool turn."""


class ToolTurnDeadlineExceeded(ToolTurnUnavailable):
    """The turn kept making progress but ran past the caller's wall-clock window.

    Callers treat this differently from a transport failure: the app-server works,
    the batch is simply too slow for the window that was granted.
    """


@dataclass(frozen=True)
class DynamicTool:
    """One host-provided tool that Codex may call inside the turn."""

    name: str
    description: str
    schema: dict[str, object]
    handler: ToolHandler


async def run_tool_turn(
    *,
    endpoint: str,
    prompt: str,
    cwd: str,
    tool_name: str,
    tool_description: str,
    tool_schema: dict[str, object],
    handler: ToolHandler,
    has_result: Callable[[], bool],
    thread_id: str = "",
    model: str = "",
    timeout_seconds: float,
    event_sink: Callable[[object], None] | None = None,
    extra_tools: Sequence[DynamicTool] = (),
    idle_timeout_seconds: float | None = None,
    host_wait_seconds: Callable[[], float] | None = None,
) -> str:
    """Run one turn and return the thread id that carried it.

    ``thread_id`` resumes a durable thread instead of starting a new one; the
    app-server restores that thread's dynamic tools, so the same contract keeps
    arriving.  ``timeout_seconds`` is a wall-clock budget for Codex' own work, not just
    the app-server's inactivity window: callers that must answer inside a caller-owned
    window cannot rely on a turn that keeps making progress, so this interrupts it at
    the deadline.  ``host_wait_seconds`` excludes time a tool handler spent waiting on
    a human, which is host latency and not Codex progress, from that budget.

    ``idle_timeout_seconds`` is the inactivity window handed to the app-server client.
    A handler that blocks on a human produces no events at all while it waits, so a
    caller with an interactive tool must pass an window longer than the longest wait it
    allows, or the turn is cancelled under the waiting user.

    Any protocol or transport failure becomes ``ToolTurnUnavailable`` so the caller can
    fall back, unless the result already arrived.
    """
    session = CodexAppServerSession(endpoint)
    session.cwd = cwd
    if model:
        session.model = model
    for tool in (
        DynamicTool(
            name=tool_name,
            description=tool_description,
            schema=tool_schema,
            handler=handler,
        ),
        *extra_tools,
    ):
        session.register_dynamic_tool(
            tool.name,
            tool.description,
            tool.schema,
            tool.handler,
        )
    used_thread = thread_id
    loop = asyncio.get_running_loop()
    try:
        try:
            if thread_id:
                await session.attach_thread(thread_id)
            else:
                await session.connect()
        except CodexAppServerError as error:
            raise ToolTurnUnavailable(str(error)) from error
        started_at = loop.time()
        deadline = started_at + timeout_seconds
        idle_timeout = (
            timeout_seconds if idle_timeout_seconds is None else idle_timeout_seconds
        )
        try:
            async for event in session.stream_turn(
                prompt,
                timeout_seconds=idle_timeout,
            ):
                if event_sink is not None:
                    event_sink(event)
                if has_result():
                    # 结果已经到手：终止本轮，避免继续消耗 token 和沙箱时间。
                    await session.interrupt()
                    break
                if host_wait_seconds is not None:
                    deadline = (
                        started_at + timeout_seconds + max(0.0, host_wait_seconds())
                    )
                if loop.time() >= deadline:
                    # 回合一直在产生进度，但已经超出调用方的窗口：主动收尾。
                    await session.interrupt()
                    raise ToolTurnDeadlineExceeded("Codex 回合超出时间预算。")
        except TimeoutError as error:
            # app-server 客户端自己的空闲超时：同样是「没在窗口内交付」。
            if not has_result():
                raise ToolTurnDeadlineExceeded(
                    str(error) or "Codex 回合超时。"
                ) from error
        except CodexAppServerError as error:
            if not has_result():
                raise ToolTurnUnavailable(str(error)) from error
        used_thread = session.thread_id or thread_id
    finally:
        await session.close()
    return used_thread
