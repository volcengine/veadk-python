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

"""Self-tests for :class:`DirectDrivingCodex`'s steering and compaction.

The runtime is about to steer in-flight turns and to rely on Codex-native
auto-compaction, so the fake must reproduce what codex 0.159.2 does (measured
against the real binary with a stub Responses server):

* ``turn.steer(input)`` lands as a user message in the running turn's *next*
  model request (never the one in flight), forcing that request even when the
  in-flight one would have ended the turn; the turn id is unchanged; a
  finished turn rejects it with ``-32600`` "no active turn to steer".
* ``thread.compact()`` returns at once and runs a separate compaction turn: a
  ``tools=[]`` request whose last user message is the CONTEXT CHECKPOINT
  COMPACTION prompt. Afterwards the history is the earlier user messages, then
  the summary message, then (re-injected) the developer message -- assistant
  replies are gone.
* ``model_auto_compact_token_limit`` compacts once the *last* response's
  ``total_tokens`` reaches the limit (``>=``): before the next turn's first
  request (inside that turn), or mid-turn before a follow-up request -- never
  at the end of the turn that crossed it. Cumulative usage does not count.

No runtime is involved; the scripted model's tool calls are answered locally,
except where a real MCP bridge proves the agent's tools are not offered to the
compaction request.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from fake_codex_sdk import (
    COMPACTION_PROMPT,
    SUMMARY_PREFIX,
    DirectDrivingCodex,
    internal_rpc_error_class,
    invalid_request_error_class,
)
from scripted_backend import Round, ScriptedBackend
from veadk.runtime.codex import rollout_io

_PROVIDER = {
    "veadk": {
        "name": "veadk",
        "base_url": "https://provider.invalid/v1",
        "env_key": "VEADK_PROVIDER_KEY",
        "wire_api": "responses",
    }
}


def _config(limit: int | None = None, **extra: Any) -> dict[str, Any]:
    config: dict[str, Any] = {"model_providers": _PROVIDER, **extra}
    if limit is not None:
        config["model_auto_compact_token_limit"] = limit
    return config


class TextInput:
    """Name-compatible with ``openai_codex.TextInput`` (the fake reads names)."""

    def __init__(self, text: str) -> None:
        self.text = text


class _Gate:
    """Wraps a model call so chosen calls block until released."""

    def __init__(self, inner: Any, block: set[int]) -> None:
        self.inner = inner
        self.block = block
        self.calls = 0
        self.entered: dict[int, asyncio.Event] = {i: asyncio.Event() for i in block}
        self.release: dict[int, asyncio.Event] = {i: asyncio.Event() for i in block}

    async def __call__(self, **kwargs: Any) -> Any:
        index = self.calls
        self.calls += 1
        if index in self.block:
            self.entered[index].set()
            await self.release[index].wait()
        return await self.inner(**kwargs)


def _client(home: Path, model_call: Any, **env: str) -> DirectDrivingCodex:
    return DirectDrivingCodex(
        config=SimpleNamespace(
            cwd=None,
            env={
                "VEADK_PROVIDER_KEY": "provider-key",
                "CODEX_HOME": str(home),
                **env,
            },
        ),
        model_call=model_call,
    )


async def _thread(codex: DirectDrivingCodex, **config: Any) -> Any:
    return await codex.thread_start(
        ephemeral=False,
        model="m",
        model_provider="veadk",
        developer_instructions="DEV-RULE",
        config=_config(**config),
    )


async def _drain(turn: Any) -> list[Any]:
    async def go() -> list[Any]:
        return [n.payload async for n in turn.stream()]

    notes = await asyncio.wait_for(go(), 30)
    assert type(notes[-1]).__name__ == "TurnCompletedNotification"
    return notes


async def _run(thread: Any, text: str) -> list[Any]:
    return await _drain(await thread.turn([TextInput(text)]))


def _texts(request: dict[str, Any], role: str) -> list[str]:
    return [
        part.get("text")
        for item in request["input"]
        if item.get("type") == "message" and item.get("role") == role
        for part in item.get("content") or []
    ]


def _roles(request: dict[str, Any]) -> list[str]:
    return [
        f"{item.get('role')}:{''.join(p.get('text', '') for p in item['content'])}"
        if item.get("type") == "message"
        else str(item.get("type"))
        for item in request["input"]
    ]


def _dump(payload: Any) -> dict[str, Any]:
    dump = payload.model_dump
    try:
        return dump(mode="json")
    except TypeError:  # the name-compatible shim takes no mode
        return dump()


def _final(notes: list[Any]) -> dict[str, Any]:
    """The ``turn`` of the closing ``turn/completed`` notification."""
    return _dump(notes[-1])["turn"]


def _item_kinds(notes: list[Any]) -> list[str]:
    """``started:userMessage:<text>`` / ``completed:contextCompaction`` ..."""
    out = []
    for note in notes:
        name = type(note).__name__
        if name not in ("ItemStartedNotification", "ItemCompletedNotification"):
            continue
        item = _dump(note)["item"]
        label = f"{name[4:-12].lower()}:{item['type']}"
        if item["type"] == "userMessage":
            label += ":" + item["content"][0]["text"]
        elif item["type"] == "agentMessage" and "Completed" in name:
            label += ":" + item["text"]  # started carries no text yet
        out.append(label)
    return out


def _summary(text: str) -> str:
    return f"{SUMMARY_PREFIX}\n{text}"


def _sampling(codex: DirectDrivingCodex) -> list[dict[str, Any]]:
    return [r for r in codex.requests if "_trigger" not in r]


# ---------------------------------------------------------------- steering


@pytest.mark.asyncio
async def test_steer_reaches_next_request_of_same_turn(tmp_path) -> None:
    backend = ScriptedBackend(
        [Round(tool_calls=(("lookup", {"q": "x"}),)), Round(text="DONE")], arm="codex"
    )
    gate = _Gate(backend.as_aresponses(), {0})
    codex = _client(tmp_path, gate)
    thread = await _thread(codex)
    turn = await thread.turn([TextInput("base")])
    drain = asyncio.create_task(_drain(turn))
    await asyncio.wait_for(gate.entered[0].wait(), 10)

    reply = await turn.steer("STEER-ONE")
    assert reply.turn_id == turn.id
    await turn.steer([TextInput("STEER-TWO")])
    gate.release[0].set()
    notes = await drain

    first, second = codex.requests
    assert _texts(first, "user") == ["base"]
    assert _texts(second, "user") == ["base", "STEER-ONE", "STEER-TWO"]
    kinds = [item.get("type") for item in second["input"]]
    # The steered messages follow the in-flight response's tool round.
    assert kinds.index("function_call_output") < len(kinds) - 2
    started = [n for n in notes if type(n).__name__ == "TurnStartedNotification"]
    assert len(started) == 1 and _final(notes)["id"] == turn.id
    assert _final(notes)["status"] == "completed"
    assert "started:userMessage:STEER-ONE" in _item_kinds(notes)
    assert [(s["turn_id"], s["text"]) for s in codex.steers] == [
        (turn.id, "STEER-ONE"),
        (turn.id, "STEER-TWO"),
    ]


@pytest.mark.asyncio
async def test_steer_during_final_answer_forces_another_request(tmp_path) -> None:
    # Real Codex: the in-flight response had no tool call, yet the steer makes
    # the turn sample again (userMessage item after the first agentMessage).
    backend = ScriptedBackend([Round(text="FIRST"), Round(text="SECOND")], arm="codex")
    gate = _Gate(backend.as_aresponses(), {0})
    codex = _client(tmp_path, gate)
    thread = await _thread(codex)
    turn = await thread.turn([TextInput("base")])
    drain = asyncio.create_task(_drain(turn))
    await asyncio.wait_for(gate.entered[0].wait(), 10)
    await turn.steer("MORE")
    gate.release[0].set()
    notes = await drain

    assert len(codex.requests) == 2
    assert _roles(codex.requests[1])[-3:] == [
        "user:base",
        "assistant:FIRST",
        "user:MORE",
    ]
    assert _item_kinds(notes) == [
        "started:userMessage:base",
        "completed:userMessage:base",
        "started:agentMessage",
        "completed:agentMessage:FIRST",
        "started:userMessage:MORE",
        "completed:userMessage:MORE",
        "started:agentMessage",
        "completed:agentMessage:SECOND",
    ]


@pytest.mark.asyncio
async def test_steer_after_completion_raises_invalid_request(tmp_path) -> None:
    backend = ScriptedBackend([Round(text="A1"), Round(text="A2")], arm="codex")
    gate = _Gate(backend.as_aresponses(), {1})
    codex = _client(tmp_path, gate)
    thread = await _thread(codex)
    first = await thread.turn([TextInput("one")])
    await _drain(first)

    error = invalid_request_error_class()
    with pytest.raises(error) as info:
        await first.steer("late")
    assert info.value.code == -32600
    assert "no active turn to steer" in info.value.message

    # A stale handle while another turn runs names both turn ids.
    second = await thread.turn([TextInput("two")])
    drain = asyncio.create_task(_drain(second))
    await asyncio.wait_for(gate.entered[1].wait(), 10)
    with pytest.raises(error) as info:
        await first.steer("stale")
    assert info.value.code == -32600
    assert f"expected active turn id {first.id} but found {second.id}" == (
        info.value.message
    )
    gate.release[1].set()
    await drain
    assert codex.steers == []
    assert all("late" not in _texts(r, "user") for r in codex.requests)


# -------------------------------------------------------- manual compaction


@pytest.mark.asyncio
async def test_compact_rewrites_history_to_user_messages_and_summary(
    tmp_path,
) -> None:
    from veadk.runtime.codex.turn_control import compact_and_wait

    backend = ScriptedBackend(
        [
            Round(tool_calls=(("lookup", {"q": "x"}),)),
            Round(text="ASSISTANT-ONE"),
            Round(text="ASSISTANT-TWO"),
            Round(text="SUMMARY-1"),
            Round(text="A3"),
        ],
        arm="codex",
    )
    gate = _Gate(backend.as_aresponses(), {3})
    codex = _client(tmp_path, gate)
    thread = await _thread(codex)
    await _run(thread, "first")
    await _run(thread, "second")

    # The runtime's primitive: compact() then poll read(include_turns=True).
    waiting = asyncio.create_task(
        compact_and_wait(thread, timeout=10, poll_interval=0.01)
    )
    await asyncio.wait_for(gate.entered[3].wait(), 10)
    # While the compaction turn runs, turn() is rejected (ActiveTurnNotSteerable)
    # and read() shows it in progress.
    with pytest.raises(internal_rpc_error_class()) as info:
        await thread.turn([TextInput("too early")])
    assert info.value.code == -32603
    assert "ActiveTurnNotSteerable" in info.value.message
    read = await thread.read(include_turns=True)
    assert read.thread.turns[-1].status == "inProgress"
    gate.release[3].set()
    assert await waiting == "completed"

    (compaction,) = codex.compactions
    assert compaction["_trigger"] == "manual"
    assert compaction["tools"] == [] and compaction["parallel_tool_calls"] is False
    assert compaction["input"][-1]["content"][0]["text"] == COMPACTION_PROMPT
    assert "ASSISTANT-TWO" in _texts(compaction, "assistant")
    assert "function_call_output" in [i.get("type") for i in compaction["input"]]

    await _run(thread, "third")
    after = codex.requests[-1]
    assert _roles(after) == [
        "user:first",
        "user:second",
        f"user:{_summary('SUMMARY-1')}",
        "developer:DEV-RULE",
        "user:third",
    ]

    turns = (await thread.read(include_turns=True)).thread.turns
    assert [t.status for t in turns] == ["completed"] * 4
    assert [[i.type for i in t.items] for t in turns] == [
        [],
        [],
        ["contextCompaction"],
        [],
    ]


@pytest.mark.asyncio
async def test_second_compaction_drops_the_first_summary(tmp_path) -> None:
    backend = ScriptedBackend(
        [
            Round(text="A1"),
            Round(text="S1"),
            Round(text="A2"),
            Round(text="S2"),
            Round(text="A3"),
        ],
        arm="codex",
    )
    codex = _client(tmp_path, backend.as_aresponses())
    thread = await _thread(codex)
    await _run(thread, "u1")
    await thread.compact()
    await thread.compaction
    await _run(thread, "u2")
    await thread.compact()
    await thread.compaction
    await _run(thread, "u3")
    assert _roles(codex.requests[-1]) == [
        "user:u1",
        "user:u2",
        f"user:{_summary('S2')}",
        "developer:DEV-RULE",
        "user:u3",
    ]
    # The second compaction still saw the first summary.
    assert _summary("S1") in _texts(codex.compactions[1], "user")


@pytest.mark.asyncio
async def test_compaction_does_not_offer_mcp_tools(tmp_path) -> None:
    from test_fake_direct_codex import TOKEN, _bridge

    async with _bridge() as bridge:
        server = {
            "url": bridge.url,
            "bearer_token_env_var": "VEADK_MCP_TOKEN",
            "default_tools_approval_mode": "approve",
        }
        backend = ScriptedBackend(
            [
                Round(tool_calls=(("echo", {"text": "hi"}),), usage=(4990, 10)),
                Round(text="SUMMARY"),
                Round(text="AFTER"),
            ],
            arm="codex",
        )
        codex = _client(tmp_path, backend.as_aresponses(), VEADK_MCP_TOKEN=TOKEN)
        thread = await _thread(codex, limit=1000, mcp_servers={"veadk": server})
        notes = await _run(thread, "one")

    first, compaction, follow_up = codex.requests
    assert [t["name"] for t in first["tools"]] == ["mcp__veadk"]
    assert [t["name"] for t in follow_up["tools"]] == ["mcp__veadk"]
    assert compaction["_trigger"] == "mid_turn" and compaction["tools"] == []
    assert "mcp__veadk" not in str(compaction["tools"])
    # Mid-turn: the MCP round is in the compaction input, gone afterwards.
    assert [i.get("type") for i in compaction["input"]].count("function_call") == 1
    assert _roles(follow_up) == [
        "developer:DEV-RULE",
        "user:one",
        f"user:{_summary('SUMMARY')}",
    ]
    kinds = [k for k in _item_kinds(notes) if "Message" in k or "Compaction" in k]
    assert kinds == [
        "started:userMessage:one",
        "completed:userMessage:one",
        "started:contextCompaction",
        "completed:contextCompaction",
        "started:agentMessage",
        "completed:agentMessage:AFTER",
    ]
    assert _final(notes)["status"] == "completed"


# ---------------------------------------------------------- auto-compaction


@pytest.mark.asyncio
async def test_auto_compaction_runs_before_the_next_turn(tmp_path) -> None:
    backend = ScriptedBackend(
        [
            Round(text="R1", usage=(4990, 10)),
            Round(text="SUMMARY"),
            Round(text="R2"),
        ],
        arm="codex",
    )
    codex = _client(tmp_path, backend.as_aresponses())
    thread = await _thread(codex, limit=1000)
    await _run(thread, "turn-one")
    await asyncio.sleep(0.05)
    # Not at the end of the turn that crossed the limit.
    assert len(codex.requests) == 1 and codex.compactions == []

    notes = await _run(thread, "turn-two")
    (compaction,) = codex.compactions
    assert compaction["_trigger"] == "pre_turn"
    assert compaction["_turn_id"] == _final(notes)["id"]
    # Before the new user message was recorded.
    assert "turn-two" not in _texts(compaction, "user")
    assert "R1" in _texts(compaction, "assistant")
    assert _roles(codex.requests[-1]) == [
        "user:turn-one",
        f"user:{_summary('SUMMARY')}",
        "developer:DEV-RULE",
        "user:turn-two",
    ]
    assert _item_kinds(notes)[:3] == [
        "started:contextCompaction",
        "completed:contextCompaction",
        "started:userMessage:turn-two",
    ]
    turns = (await thread.read(include_turns=True)).thread.turns
    assert [[i.type for i in t.items] for t in turns] == [[], ["contextCompaction"]]


@pytest.mark.asyncio
@pytest.mark.parametrize(("total", "compacts"), [(999, False), (1000, True)])
async def test_auto_compaction_threshold_is_inclusive(
    tmp_path, total: int, compacts: bool
) -> None:
    backend = ScriptedBackend(
        [Round(text="R1", usage=(total - 10, 10)), Round(text="S"), Round(text="R2")],
        arm="codex",
    )
    codex = _client(tmp_path, backend.as_aresponses())
    thread = await _thread(codex, limit=1000)
    await _run(thread, "one")
    await _run(thread, "two")
    assert bool(codex.compactions) is compacts


@pytest.mark.asyncio
async def test_cumulative_usage_does_not_trigger_auto_compaction(tmp_path) -> None:
    backend = ScriptedBackend(
        [Round(text=f"R{i}", usage=(390, 10)) for i in range(4)], arm="codex"
    )
    codex = _client(tmp_path, backend.as_aresponses())
    thread = await _thread(codex, limit=1000)
    for i in range(4):
        await _run(thread, f"t{i}")
    assert codex.compactions == [] and len(codex.requests) == 4


@pytest.mark.asyncio
async def test_no_limit_never_auto_compacts(tmp_path) -> None:
    backend = ScriptedBackend(
        [Round(text="R1", usage=(99990, 10)), Round(text="R2")], arm="codex"
    )
    codex = _client(tmp_path, backend.as_aresponses())
    thread = await _thread(codex)
    await _run(thread, "one")
    await _run(thread, "two")
    assert codex.compactions == []


# ------------------------------------------------------------------ resume


async def _move(home1: Path, home2: Path, thread_id: str) -> None:
    rollout = rollout_io.export_rollout(str(home1), thread_id)
    assert rollout is not None
    rollout_io.import_rollout(str(home2), rollout)


@pytest.mark.asyncio
async def test_compaction_survives_export_import_resume(tmp_path) -> None:
    backend = ScriptedBackend(
        [Round(text="OLD-ANSWER"), Round(text="SUMMARY-X"), Round(text="NEW")],
        arm="codex",
    )
    codex = _client(tmp_path / "home1", backend.as_aresponses())
    thread = await _thread(codex)
    await _run(thread, "remember")
    await thread.compact()
    await thread.compaction
    await _move(tmp_path / "home1", tmp_path / "home2", thread.id)

    codex2 = _client(tmp_path / "home2", backend.as_aresponses())
    resumed = await codex2.thread_resume(
        thread.id,
        model="m",
        model_provider="veadk",
        config=_config(),
        developer_instructions="DEV-RESUMED",
    )
    await _run(resumed, "after")
    (request,) = codex2.requests
    # Codex re-injects the *resume* call's developer instructions.
    assert _roles(request) == [
        "user:remember",
        f"user:{_summary('SUMMARY-X')}",
        "developer:DEV-RESUMED",
        "user:after",
    ]
    assert "OLD-ANSWER" not in str(request["input"])
    turns = (await resumed.read(include_turns=True)).thread.turns
    assert [[i.type for i in t.items] for t in turns] == [
        [],
        ["contextCompaction"],
        [],
    ]


@pytest.mark.asyncio
async def test_resume_with_limit_compacts_on_persisted_usage(tmp_path) -> None:
    # Real Codex: a thread started without a limit, resumed in a new process
    # with one, compacts before its first turn if the last response (from the
    # earlier process) was already over it.
    backend = ScriptedBackend(
        [Round(text="R1", usage=(4990, 10)), Round(text="S"), Round(text="R2")],
        arm="codex",
    )
    codex = _client(tmp_path / "home1", backend.as_aresponses())
    thread = await _thread(codex)
    await _run(thread, "one")
    assert codex.compactions == []
    await _move(tmp_path / "home1", tmp_path / "home2", thread.id)

    codex2 = _client(tmp_path / "home2", backend.as_aresponses())
    resumed = await codex2.thread_resume(
        thread.id, model="m", model_provider="veadk", config=_config(limit=1000)
    )
    await _run(resumed, "two")
    assert [r["_trigger"] for r in codex2.compactions] == ["pre_turn"]
    assert _texts(codex2.requests[-1], "user")[-1] == "two"
    assert len(_sampling(codex2)) == 1
