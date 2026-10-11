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

"""``Runner.steer``: routing a steer to the runtime that runs the turn.

The runner does not know which agent of a multi-agent tree is mid-turn, so it
offers the text to every non-``adk`` agent's runtime until one takes it. These
tests replace ``veadk.runtime.get_runtime`` with a recording fake, so they pin
the routing (which agents, which session key) without running a turn.
"""

from __future__ import annotations

from typing import Any

import pytest

from veadk import Agent
from veadk.runner import Runner, _descendants

_MODEL = {
    "model_name": "scripted-model",
    "model_api_base": "https://backend.invalid/v1",
    "model_api_key": "backend-key",
}


def _agent(name: str, *, runtime: str = "adk", sub_agents=()) -> Agent:
    return Agent(
        name=name,
        description=f"The {name} agent.",
        instruction="Answer.",
        runtime=runtime,
        sub_agents=list(sub_agents),
        **_MODEL,
    )


class _FakeRuntime:
    """Records every steer; answers with ``delivers`` (per agent name)."""

    def __init__(self, delivers: dict[str, bool]) -> None:
        self.delivers = delivers
        self.calls: list[dict[str, Any]] = []

    async def steer(self, agent: Any, **kwargs: Any) -> bool:
        self.calls.append({"agent": agent.name, **kwargs})
        return self.delivers.get(agent.name, False)


def _install(monkeypatch: pytest.MonkeyPatch, runtime: _FakeRuntime) -> list[str]:
    """Route every ``get_runtime(name)`` to ``runtime``; return the names asked."""
    import veadk.runtime

    asked: list[str] = []

    def fake_get_runtime(name: str) -> _FakeRuntime:
        asked.append(name)
        return runtime

    monkeypatch.setattr(veadk.runtime, "get_runtime", fake_get_runtime)
    return asked


def test_descendants_is_depth_first_over_the_whole_tree() -> None:
    """A codex agent can sit below an adk coordinator at any depth."""
    leaf = _agent("leaf", runtime="codex")
    mid = _agent("mid", sub_agents=[leaf])
    sibling = _agent("sibling")
    root = _agent("root", sub_agents=[mid, sibling])

    assert [a.name for a in _descendants(root)] == ["mid", "leaf", "sibling"]
    assert _descendants(leaf) == []


@pytest.mark.asyncio
async def test_steer_reaches_codex_sub_agent_with_the_session_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The steer must reach the sub-agent's runtime under the turn's own key.

    The codex runtime finds the running turn by ``(app, user, session,
    agent)``. A wrong app name, or an empty user id where the turn was run
    under the runner's default user, would miss the turn and the steer would
    be silently dropped.
    """
    coder = _agent("coder", runtime="codex")
    root = _agent("root", sub_agents=[_agent("mid", sub_agents=[coder])])
    runner = Runner(agent=root, app_name="steer_app", user_id="default_user")
    runtime = _FakeRuntime({"coder": True})
    asked = _install(monkeypatch, runtime)

    assert await runner.steer("session-1", "use the staging table") is True
    assert asked == ["codex"]
    assert runtime.calls == [
        {
            "agent": "coder",
            "app_name": "steer_app",
            "user_id": "default_user",
            "session_id": "session-1",
            "text": "use the staging table",
        }
    ]

    runtime.calls.clear()
    assert await runner.steer("session-2", "stop", user_id="alice") is True
    assert runtime.calls[0]["user_id"] == "alice"
    assert runtime.calls[0]["session_id"] == "session-2"


@pytest.mark.asyncio
async def test_steer_returns_false_when_no_runtime_delivers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No running turn means ``False``, after every candidate was offered it.

    A caller uses the result to decide whether to start a new turn instead; a
    ``True`` here would make it drop the user's message.
    """
    root = _agent(
        "root",
        sub_agents=[
            _agent("coder_a", runtime="codex"),
            _agent("coder_b", runtime="codex"),
        ],
    )
    runner = Runner(agent=root, app_name="steer_app", user_id="u")
    runtime = _FakeRuntime({})
    _install(monkeypatch, runtime)

    assert await runner.steer("session-1", "hello") is False
    assert [c["agent"] for c in runtime.calls] == ["coder_a", "coder_b"]


@pytest.mark.asyncio
async def test_steer_stops_at_the_first_runtime_that_delivers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One steer, one turn: once delivered it is not offered to other agents."""
    root = _agent(
        "root",
        sub_agents=[
            _agent("coder_a", runtime="codex"),
            _agent("coder_b", runtime="codex"),
        ],
    )
    runner = Runner(agent=root, app_name="steer_app", user_id="u")
    runtime = _FakeRuntime({"coder_a": True, "coder_b": True})
    _install(monkeypatch, runtime)

    assert await runner.steer("session-1", "hello") is True
    assert [c["agent"] for c in runtime.calls] == ["coder_a"]


@pytest.mark.asyncio
async def test_pure_adk_tree_returns_false_without_touching_a_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``runtime="adk"`` has no steerable turn; no runtime may be consulted.

    ADK runs its turns inline, so no runtime holds a turn for an adk agent,
    and ``get_runtime("adk")`` would raise instead of answering ``False``.
    """
    root = _agent("root", sub_agents=[_agent("helper")])
    runner = Runner(agent=root, app_name="steer_app", user_id="u")
    runtime = _FakeRuntime({"root": True, "helper": True})
    asked = _install(monkeypatch, runtime)

    assert await runner.steer("session-1", "hello") is False
    assert asked == [] and runtime.calls == []
