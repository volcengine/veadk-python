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

"""Runtime-agnostic harness for the runtime conformance suite.

The differential suite answers "do ``adk`` and ``codex`` agree?". This suite
answers a different question -- "does *this* runtime honour the contract every
runtime owes the ``Runner``?" -- so a runtime can be checked on its own, and a
new runtime (or a rewrite of an old one) only has to supply a
:class:`RuntimeAdapter` and a capability set.

The contract is stated in terms only the ``Runner`` and the model can observe:

* the ADK events a turn yields and the session it leaves behind;
* :class:`ModelRequest` -- what the backend was *asked*, flattened to text,
  because the runtimes serialize the conversation in incompatible shapes
  (ADK ``contents``, a Codex prompt blob, a Pi prompt plus tool results) and
  the scenarios only ever need "does the model see X?";
* per-runtime resources, reported by :meth:`RuntimeAdapter.leaks` as a list of
  human-readable problems so that a scenario can assert ``== []`` without
  knowing what a shim turn or a ``CODEX_HOME`` is.

Everything goes through the real ``google.adk`` ``Runner`` and a real
``veadk.Agent``; only the model is scripted (``scripted_backend.Round``).
"""

from __future__ import annotations

import asyncio
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

import pytest
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types

from scripted_backend import Round


class Capability:
    """Capability names a runtime adapter may declare.

    A required scenario runs for every runtime. A scenario gated on one of these
    runs only when the adapter declares it, and is otherwise skipped with a
    reason naming the missing capability -- so a redesign PR that implements,
    say, thread resume turns the scenario on by adding one name to its
    adapter's set, and cannot claim the capability without passing it.
    """

    RESUME_ACROSS_RESTART = "resume_across_restart"
    STEER = "steer"
    TURN_TIMEOUT = "turn_timeout"
    COMPACTION = "compaction"
    APPROVALS = "approvals"
    MCP_TOOLS = "mcp_tools"
    SKILLS = "skills"

    ALL = frozenset(
        {
            RESUME_ACROSS_RESTART,
            STEER,
            TURN_TIMEOUT,
            COMPACTION,
            APPROVALS,
            MCP_TOOLS,
            SKILLS,
        }
    )


class HangForever(Exception):
    """Marker for a :class:`Round` whose model call never returns.

    Put ``Round(raises=HangForever())`` in a plan; each adapter intercepts it
    *before* it can propagate and instead blocks the backend call until the
    runtime abandons it. That is what lets the cancellation scenario cancel a
    turn that is provably waiting on the model rather than one that happened to
    be between awaits.
    """


#: A plan round that blocks the backend forever.
HANG = Round(raises=HangForever())


@dataclass(frozen=True)
class ModelRequest:
    """One backend model call, as the scripted model saw it.

    Attributes:
        text: Everything visible to the model, flattened (system/developer
            instructions, conversation history, the current message, tool
            results, and -- for runtimes that materialize them -- skills).
            Scenarios assert containment of unique markers in it, never shape.
        tool_names: The function tools advertised on this request.
    """

    text: str
    tool_names: tuple[str, ...] = ()


@dataclass
class ScriptedAgent:
    """An agent wired to its own scripted backend, as built by an adapter."""

    key: str
    agent: Any
    plan: tuple[Round, ...]


@dataclass
class TurnResult:
    """What one ``Runner.run_async`` call produced."""

    events: list[Any]
    error: BaseException | None
    session: Any
    session_id: str

    @property
    def finals(self) -> list[Any]:
        """Final responses that actually carry content."""
        return [
            e
            for e in self.events
            if e.is_final_response() and e.content and e.content.parts
        ]

    @property
    def final_text(self) -> str:
        texts: list[str] = []
        for event in self.finals:
            for part in event.content.parts:
                if part.text and not part.thought:
                    texts.append(part.text)
        return "".join(texts).strip()


@dataclass
class HangProbe:
    """Tracks a backend call parked on :data:`HANG`."""

    entered: asyncio.Event = field(default_factory=asyncio.Event)
    abandoned: bool = False


class RuntimeAdapter(ABC):
    """How the conformance scenarios drive one runtime.

    Subclasses bind a runtime to the offline doubles it needs. Everything the
    scenarios need goes through this interface, so adding a runtime is one
    subclass plus an entry in ``conftest.ADAPTERS``.

    Attributes:
        name: The ``Agent(runtime=...)`` value.
        capabilities: Subset of :attr:`Capability.ALL` this runtime implements.
        streams_partials: Whether a text turn is expected to yield ``partial``
            events before the final response. Not a gate: the streaming
            scenario runs for everyone, and only its "saw at least one partial"
            half depends on this.
        skill_discovery_tool: See the attribute comment below.
    """

    name: str = ""
    capabilities: frozenset[str] = frozenset()
    streams_partials: bool = False
    #: The tool a model calls to discover skills, when the runtime does not
    #: put them in front of the model on its own (ADK's ``SkillToolset``).
    skill_discovery_tool: str | None = None

    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        self.monkeypatch = monkeypatch
        self.tmp_path = tmp_path

    # ----------------------------------------------------------- lifecycle

    def setup(self) -> None:
        """Install offline doubles. Called once per test before any build."""

    def teardown(self) -> None:
        """Remove process-global state. Must be idempotent."""

    # ---------------------------------------------------------------- build

    @abstractmethod
    def build(
        self,
        plan: Iterable[Round],
        *,
        key: str = "main",
        tools: Sequence[Any] = (),
        **agent_kwargs: Any,
    ) -> ScriptedAgent:
        """Build an agent whose model replays ``plan``.

        ``key`` names the backend: each key gets its own plan cursor and
        request log, which is what lets two agents run concurrently without a
        shared script. Building an existing key again replaces its plan and
        restarts its cursor; its request log keeps accumulating.
        """

    # ----------------------------------------------------------- observing

    @abstractmethod
    def requests(self, key: str = "main") -> list[ModelRequest]:
        """Every model call the backend for ``key`` received, in order."""

    def hang_probe(self, key: str = "main") -> HangProbe:
        """The probe for a :data:`HANG` round in ``key``'s plan."""
        probes = self.__dict__.setdefault("_hang_probes", {})
        return probes.setdefault(key, HangProbe())

    async def wait_for_hang(self, key: str = "main", timeout: float = 30.0) -> bool:
        """Wait until ``key``'s backend is parked on a :data:`HANG` round."""
        try:
            await asyncio.wait_for(self.hang_probe(key).entered.wait(), timeout)
        except asyncio.TimeoutError:
            return False
        return True

    def hang_abandoned(self, key: str = "main") -> bool:
        """Whether the backend work parked on :data:`HANG` has been stopped."""
        return self.hang_probe(key).abandoned

    @abstractmethod
    def leaks(self) -> list[str]:
        """Per-turn resources still held after every turn has ended."""

    @abstractmethod
    def runtime_entrypoint(self) -> tuple[Any, str]:
        """``(owner, attribute)`` of the async generator that *is* the runtime.

        The cancellation scenario wraps it to record how the runtime itself
        ended: ADK's ``Runner`` re-raises ``CancelledError`` on its own once its
        task is cancelled, so a runtime that swallowed the cancellation would
        still look correct from outside.
        """

    # ------------------------------------------------- capability-gated hooks

    def mcp_toolset(self) -> Any:
        """An MCP toolset the agent can call, for :attr:`Capability.MCP_TOOLS`.

        The repo's demo stdio server: a real MCP subprocess, no network.
        """
        import sys
        from pathlib import Path

        from google.adk.tools.mcp_tool.mcp_session_manager import (
            StdioServerParameters,
        )
        from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

        server = (
            Path(__file__).resolve().parents[3]
            / "examples"
            / "piagent_with_mcp"
            / "mcp_order_server.py"
        )
        return McpToolset(
            connection_params=StdioServerParameters(
                command=sys.executable, args=[str(server)]
            )
        )

    def restart(self) -> None:
        """Simulate a process restart between turns (resume_across_restart)."""
        raise NotImplementedError

    def native_thread_id(self, session_id: str) -> str | None:
        """The runtime's own conversation handle for a session, if any."""
        raise NotImplementedError

    async def steer(self, session_id: str, text: str) -> None:
        """Deliver ``text`` into the in-flight turn of ``session_id``."""
        raise NotImplementedError

    def turn_timeout_kwargs(self, seconds: float) -> dict[str, Any]:
        """Agent kwargs that bound one turn to ``seconds``."""
        raise NotImplementedError

    def compaction_kwargs(self) -> dict[str, Any]:
        """Agent kwargs that make the runtime compact after a single turn."""
        raise NotImplementedError

    def require(self, capability: str) -> None:
        """Skip the calling scenario unless this runtime declares ``capability``."""
        assert capability in Capability.ALL, capability
        if capability not in self.capabilities:
            pytest.skip(
                f"runtime {self.name!r} does not declare capability "
                f"{capability!r} (declared: {sorted(self.capabilities) or 'none'})"
            )


class ConformanceHarness:
    """Runs turns for one adapter through the real ``Runner``.

    One ``InMemorySessionService`` per harness: sessions persist across the
    turns of a test (multi-turn, isolation) and nothing persists across tests.
    """

    APP_NAME = "conformance"
    USER_ID = "user"

    def __init__(self, adapter: RuntimeAdapter) -> None:
        self.adapter = adapter
        self.session_service = InMemorySessionService()
        self.runtime_exits: list[BaseException | None] = []
        self._exit_recorder_installed = False

    async def new_session(self) -> str:
        session_id = f"session-{uuid.uuid4().hex[:10]}"
        await self.session_service.create_session(
            app_name=self.APP_NAME, user_id=self.USER_ID, session_id=session_id
        )
        return session_id

    async def run_turn(
        self,
        scripted: ScriptedAgent,
        session_id: str,
        text: str | None = None,
        *,
        message: types.Content | None = None,
        run_config: Any = None,
    ) -> TurnResult:
        """Run one invocation. The error, if any, is returned, never raised.

        ``CancelledError`` is the exception: it is re-raised so a cancelled
        task still reads as cancelled to the scenario that cancelled it.
        """
        runner = Runner(
            app_name=self.APP_NAME,
            agent=scripted.agent,
            session_service=self.session_service,
        )
        if message is None:
            message = types.Content(role="user", parts=[types.Part(text=text or "")])
        events: list[Any] = []
        error: BaseException | None = None
        try:
            async for event in runner.run_async(
                user_id=self.USER_ID,
                session_id=session_id,
                new_message=message,
                **({"run_config": run_config} if run_config is not None else {}),
            ):
                events.append(event)
        except asyncio.CancelledError:
            raise
        except BaseException as e:  # noqa: BLE001 - the error IS the observable
            error = e
        session = await self.session_service.get_session(
            app_name=self.APP_NAME, user_id=self.USER_ID, session_id=session_id
        )
        return TurnResult(
            events=events, error=error, session=session, session_id=session_id
        )

    def record_runtime_exits(self) -> None:
        """Wrap the runtime's own generator and record how each run ended."""
        if self._exit_recorder_installed:
            return
        self._exit_recorder_installed = True
        owner, attribute = self.adapter.runtime_entrypoint()
        original = getattr(owner, attribute)
        exits = self.runtime_exits

        def recording(*args: Any, **kwargs: Any) -> Any:
            async def _gen() -> Any:
                try:
                    async for event in original(*args, **kwargs):
                        yield event
                except BaseException as e:  # noqa: BLE001 - recorded, re-raised
                    exits.append(e)
                    raise
                exits.append(None)

            return _gen()

        self.adapter.monkeypatch.setattr(owner, attribute, recording)


# ------------------------------------------------------------------ helpers


def request_texts(requests: Sequence[ModelRequest]) -> list[str]:
    return [request.text for request in requests]


def marker(label: str) -> str:
    """A unique token, so containment can never match by coincidence."""
    return f"{label}-{uuid.uuid4().hex[:8]}"


def pending_tasks() -> set[asyncio.Task[Any]]:
    current = asyncio.current_task()
    return {t for t in asyncio.all_tasks() if t is not current and not t.done()}


async def settle(rounds: int = 20) -> None:
    """Give just-cancelled tasks and closing transports a few loop turns."""
    for _ in range(rounds):
        await asyncio.sleep(0)
    await asyncio.sleep(0.05)


async def wait_until(
    predicate: Callable[[], bool], *, timeout: float = 10.0, interval: float = 0.02
) -> bool:
    """Poll ``predicate`` until it holds or ``timeout`` passes."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return predicate()


__all__ = [
    "HANG",
    "Capability",
    "ConformanceHarness",
    "HangForever",
    "HangProbe",
    "ModelRequest",
    "Round",
    "RuntimeAdapter",
    "ScriptedAgent",
    "TurnResult",
    "marker",
    "pending_tasks",
    "request_texts",
    "settle",
    "wait_until",
]
