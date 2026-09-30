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

"""Self-tests for :class:`DirectDrivingCodex`'s persistent-thread behaviour.

The runtime is moving to one persistent Codex thread per session, resumed in a
fresh ``AsyncCodex`` process (fresh ``CODEX_HOME``) on every invocation after
VeADK imports the thread's rollout file. These tests pin the fake to the real
Codex facts that design relies on -- rollout path pattern, full-history
restore from the file alone, original developer message kept, unknown-id
resume rejected, ephemeral threads writing nothing -- with no runtime and no
MCP server (the scripted model's tool calls are answered locally).
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from fake_codex_sdk import DirectDrivingCodex, invalid_request_error_class
from scripted_backend import Round, ScriptedBackend
from veadk.runtime.codex import rollout_io

_ROLLOUT_RE = re.compile(
    r"^sessions/\d{4}/\d{2}/\d{2}/"
    r"rollout-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-(?P<id>[0-9a-f-]{36})\.jsonl$"
)
_CONFIG = {
    "model_providers": {
        "veadk": {
            "name": "veadk",
            "base_url": "https://provider.invalid/v1",
            "env_key": "VEADK_PROVIDER_KEY",
            "wire_api": "responses",
        }
    }
}


class TextInput:
    """Name-compatible with ``openai_codex.TextInput`` (the fake reads names)."""

    def __init__(self, text: str) -> None:
        self.text = text


def _client(home: Path, backend: ScriptedBackend) -> DirectDrivingCodex:
    return DirectDrivingCodex(
        config=SimpleNamespace(
            cwd=None,
            env={"VEADK_PROVIDER_KEY": "provider-key", "CODEX_HOME": str(home)},
        ),
        model_call=backend.as_aresponses(),
    )


async def _run(thread: Any, text: str) -> list[Any]:
    turn = await thread.turn([TextInput(text)])

    async def drain() -> list[Any]:
        return [n.payload async for n in turn.stream()]

    notes = await asyncio.wait_for(drain(), 30)
    assert type(notes[-1]).__name__ == "TurnCompletedNotification"
    return notes


def _texts(request: dict[str, Any], role: str) -> list[str]:
    return [
        part.get("text")
        for item in request["input"]
        if item.get("type") == "message" and item.get("role") == role
        for part in item.get("content") or []
    ]


async def _first_session(home: Path, backend: ScriptedBackend) -> tuple[Any, str]:
    codex = _client(home, backend)
    thread = await codex.thread_start(
        ephemeral=False,
        model="model-a",
        model_provider="veadk",
        developer_instructions="ORIGINAL-DEV",
        config=_CONFIG,
    )
    await _run(thread, "REMEMBER-ME")
    return codex, thread.id


@pytest.mark.asyncio
async def test_persistent_thread_writes_one_exportable_rollout(tmp_path) -> None:
    backend = ScriptedBackend([Round(text="A1")], arm="codex")
    codex, thread_id = await _first_session(tmp_path, backend)

    rollout_io.validate_thread_id(thread_id)
    files = list((tmp_path / "sessions").rglob("*.jsonl"))
    assert len(files) == 1
    relpath = files[0].relative_to(tmp_path).as_posix()
    match = _ROLLOUT_RE.match(relpath)
    assert match and match["id"] == thread_id, relpath

    rollout = rollout_io.export_rollout(str(tmp_path), thread_id)
    assert rollout is not None and rollout.relpath == relpath
    kinds = [json.loads(line)["type"] for line in rollout.data.splitlines()]
    assert kinds[0] == "session_meta"
    assert "response_item" in kinds and kinds[-1] == "turn_completed"
    assert codex.thread_starts[0]["ephemeral"] is False


@pytest.mark.asyncio
async def test_resume_in_fresh_home_restores_full_history(tmp_path) -> None:
    backend = ScriptedBackend(
        [
            Round(tool_calls=(("lookup", {"q": "x"}),)),
            Round(text="ASSISTANT-ONE"),
            Round(text="ASSISTANT-TWO"),
        ],
        arm="codex",
    )
    _, thread_id = await _first_session(tmp_path / "home1", backend)
    rollout = rollout_io.export_rollout(str(tmp_path / "home1"), thread_id)
    assert rollout is not None

    # A new process: fresh CODEX_HOME holding nothing but the rollout.
    home2 = tmp_path / "home2"
    rollout_io.import_rollout(str(home2), rollout)
    codex2 = _client(home2, backend)
    thread = await codex2.thread_resume(
        thread_id,
        include_turns=False,
        model="model-b",
        model_provider="veadk",
        config=_CONFIG,
        developer_instructions="NEW-DEV",
    )
    assert thread.id == thread_id
    await _run(thread, "what did I say?")

    (request,) = codex2.requests
    users = _texts(request, "user")
    assert users.count("REMEMBER-ME") == 1
    assert users[-1] == "what did I say?"
    assert "ASSISTANT-ONE" in _texts(request, "assistant")
    kinds = [item.get("type") for item in request["input"]]
    assert "function_call" in kinds and "function_call_output" in kinds
    # Real Codex keeps the original developer message; the new one is ignored.
    assert _texts(request, "developer") == ["ORIGINAL-DEV"]
    assert request["model"] == "model-b"
    assert request["_provider"]["api_key"] == "provider-key"
    assert codex2.thread_resumes == [
        {
            "thread_id": thread_id,
            "include_turns": False,
            "model": "model-b",
            "model_provider": "veadk",
            "config": _CONFIG,
            "developer_instructions": "NEW-DEV",
        }
    ]

    # The resumed thread keeps appending to the same (single) rollout file.
    again = rollout_io.export_rollout(str(home2), thread_id)
    assert again is not None and again.relpath == rollout.relpath
    assert len(again.data) > len(rollout.data)
    read = await thread.read(include_turns=True)
    assert [t.status for t in read.thread.turns] == ["completed", "completed"]


@pytest.mark.asyncio
async def test_second_turn_on_same_thread_sees_the_first(tmp_path) -> None:
    backend = ScriptedBackend([Round(text="A1"), Round(text="A2")], arm="codex")
    codex = _client(tmp_path, backend)
    thread = await codex.thread_start(
        ephemeral=False, model="m", model_provider="veadk", config=_CONFIG
    )
    await _run(thread, "first")
    await _run(thread, "second")
    assert _texts(codex.requests[-1], "user") == ["first", "second"]
    assert _texts(codex.requests[-1], "assistant") == ["A1"]


@pytest.mark.asyncio
async def test_resume_unknown_thread_raises_invalid_request(tmp_path) -> None:
    codex = _client(tmp_path, ScriptedBackend([], arm="codex"))
    error = invalid_request_error_class()
    for bad in ("0b7c7c4e-0000-4000-8000-000000000000", "../etc"):
        with pytest.raises(error) as info:
            await codex.thread_resume(bad, model="m", config=_CONFIG)
        assert info.value.code == -32600
    assert codex.requests == []


@pytest.mark.asyncio
async def test_ephemeral_thread_writes_no_rollout(tmp_path) -> None:
    backend = ScriptedBackend([Round(text="A1")], arm="codex")
    codex = _client(tmp_path, backend)
    thread = await codex.thread_start(
        ephemeral=True, model="m", model_provider="veadk", config=_CONFIG
    )
    await _run(thread, "hi")
    assert not (tmp_path / "sessions").exists()
    assert rollout_io.export_rollout(str(tmp_path), thread.id) is None
    with pytest.raises(invalid_request_error_class()):
        await thread.read(include_turns=True)
