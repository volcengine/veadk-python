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

"""The running Codex turn's workspace, as an ADK tool sees it.

Why a tool needs this
---------------------

Under ``runtime="codex"`` the two halves of a turn run in different places.
Codex runs in a sandboxed subprocess whose ``cwd`` is a per-session workspace
directory; the agent's ADK tools run in the host process, outside that sandbox.
So the supported way for a tool to hand Codex data is to **write a file into
that workspace and return its path** — never to return the payload, which the
shim serializes into the model's context and replays on every later request of
the turn.

That leaves the tool needing the path, and it cannot derive one: the workspace
is keyed by a private digest over app/user/session/agent (see
:func:`veadk.runtime.codex.runtime._prepare_workspace`). Pinning
``workspace_root`` together with ``reuse_workspace`` makes it predictable, but
collapses every session onto one directory — acceptable for a single-user demo,
not for a multi-tenant server. :func:`current_workspace` is the supported
alternative, and it works with both left unset.

Why the value is bound at *tool-call* time
------------------------------------------

The obvious shape — set a ``ContextVar`` in ``run_async`` and read it in the
tool — does not work, and fails in the worst possible way. ADK tools are run by
the Responses shim, in a request handler that descends from the uvicorn server
task, and that task's context was snapshotted by ``asyncio.create_task`` when
the *first* invocation in the process started the shim. Measured against a real
shim (var set in the invocation's own task, three later turns on the same
shim): every later turn's tool read the **first** turn's value. A plain
"contextvar set in ``run_async``" is therefore not a miss but a silent
cross-tenant leak. The same asymmetry is why the shim has to capture an OTel
context at ``register_turn`` and re-attach it around tool execution; see
``proxy.ShimTurnContext.otel_context``.

Nothing here reads ambient context to *find* the workspace, then. The runtime
wraps each turn's executors with :func:`bind_workspace_to_executors`, which
captures the workspace in a closure, and every wrapper sets the ``ContextVar``
around its own call. Whichever task the shim runs an executor on, the value is
set in *that* task's context — ``asyncio.gather`` gives each concurrent call its
own context copy — so a tool can read it ambiently while the binding itself can
never be inherited by the wrong turn.
"""

from __future__ import annotations

import contextlib
import contextvars
from typing import Any, Awaitable, Callable, Iterator

#: ``name -> async (args, call_id) -> str``, as built by
#: :mod:`veadk.runtime.codex.tools_bridge` and consumed by the shim.
Executor = Callable[[dict[str, Any], str], Awaitable[str]]

_CURRENT_WORKSPACE: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "veadk_codex_current_workspace", default=None
)


def current_workspace() -> str | None:
    """Absolute path of the workspace Codex is using for the current tool call.

    Call this from an ADK tool running under ``runtime="codex"`` to find the
    directory the sandbox is working in, then write files there and return
    their paths to the model instead of their contents.

    Returns ``None`` (rather than raising) when there is no Codex turn on this
    call stack — the same tool object is routinely executed by other runtimes,
    by ``AgentTool``, and by unit tests, and a tool that can branch on ``None``
    stays usable in all of them. A tool that genuinely cannot work without the
    workspace should return its own ``{"status": "error", ...}`` result, which
    the model can act on, rather than raising out of the tool.

    Returns:
        str | None: The turn's workspace directory, or ``None`` outside a
        Codex tool call.

    Example:
        ::

            from pathlib import Path

            from veadk.runtime.codex import current_workspace


            def fetch_orders(quarter: str) -> dict:
                \"\"\"Write a quarter of orders into your working directory.\"\"\"
                workspace = current_workspace()
                if workspace is None:
                    return {"status": "error", "message": "no codex workspace"}
                destination = Path(workspace) / "data" / f"{quarter}.csv"
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(export_orders(quarter), encoding="utf-8")
                # A receipt, not the rows: the rows would be replayed into the
                # model's context on every later request of this turn.
                return {"status": "ok", "path": f"data/{quarter}.csv"}
    """
    return _CURRENT_WORKSPACE.get()


@contextlib.contextmanager
def bind_workspace(workspace: str) -> Iterator[None]:
    """Make ``workspace`` the value :func:`current_workspace` returns.

    Scoped to the block *and* to the task running it: a ``ContextVar`` set here
    is visible to everything this task awaits (including tasks it spawns, which
    copy the context at creation) and to nothing else.

    Args:
        workspace (str): Absolute path of the turn's workspace.

    Yields:
        None: For the duration of the binding.
    """
    token = _CURRENT_WORKSPACE.set(workspace)
    try:
        yield
    finally:
        _CURRENT_WORKSPACE.reset(token)


def bind_workspace_to_executors(
    executors: dict[str, Executor], workspace: str
) -> dict[str, Executor]:
    """Wrap tool executors so each call runs with ``workspace`` bound.

    The workspace is captured in the wrapper's closure rather than read from
    ambient context, which is what makes this correct wherever the shim decides
    to run the executor: the shim's handler task does not inherit the
    invocation's context (see the module docstring), so a value the invocation
    merely *set* would not be there — or, worse, a value another invocation set
    before the shim started would be.

    Args:
        executors (dict[str, Executor]): The turn's tool executors.
        workspace (str): Absolute path of the turn's workspace.

    Returns:
        dict[str, Executor]: Executors of the same shape, each binding the
        workspace for the duration of its own call.
    """

    def _bind(executor: Executor) -> Executor:
        async def _run(args: dict[str, Any], call_id: str) -> str:
            with bind_workspace(workspace):
                return await executor(args, call_id)

        return _run

    return {name: _bind(executor) for name, executor in executors.items()}
