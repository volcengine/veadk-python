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

"""Exercise recovery decisions against a real task database."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from frontend.server.intelligent_development import StudioCredentials
from frontend.server.intelligent_development_runs.repository import RunRepository
from frontend.server.intelligent_development_runs.runner import DevelopmentRunner
from veadk.cli.codex_app_server import CodexAppServerEvent


@pytest.mark.asyncio
async def test_observing_existing_turn_does_not_acknowledge_unsent_steer(tmp_path):
    repository = RunRepository(tmp_path / "runs.db")
    run = await repository.create("alice", "environment", "initial", "build")
    token = await repository.claim("alice", run.id)
    assert token
    await repository.input_status(
        "alice", run.id, token, "initial", "delivered", turn_id="turn-1"
    )
    await repository.add_input("alice", run.id, "steer", "change the requirement")
    await repository.checkpoint("alice", run.id, token, accepted_revision=1)
    run = await repository.update(
        "alice", run.id, token, phase="coding", turn_id="turn-1"
    )

    class Codex:
        thread_id = "thread-1"

        async def stream_turn(self, prompt, **options):
            assert prompt == ""
            assert options["resume_turn_id"] == "turn-1"
            yield CodexAppServerEvent(kind="turn_started", turn_id="turn-1")

    runner = DevelopmentRunner(
        repository,
        resolve_session=AsyncMock(),
        workspace=lambda _: "/workspace",
        credentials=lambda: StudioCredentials("", ""),
        render_event=lambda *_: None,
    )
    await runner._coding(
        run,
        token,
        cast(Any, Codex()),
        cast(Any, SimpleNamespace(exact_secrets=())),
        cast(Any, SimpleNamespace()),
        "/workspace",
    )
    inputs = await repository.inputs("alice", run.id)
    assert inputs[1]["status"] == "pending"
    assert (await repository.get("alice", run.id)).checkpoint["accepted_revision"] == 1


@pytest.mark.asyncio
async def test_stop_cannot_resurrect_withdrawn_input(tmp_path):
    from frontend.server.intelligent_development_runs.repository import RunConflict

    repository = RunRepository(tmp_path / "runs.db")
    run = await repository.create("alice", "environment", "initial", "build")
    token = await repository.claim("alice", run.id)
    assert token
    await repository.request_stop("alice", run.id)
    with pytest.raises(RunConflict):
        await repository.input_status("alice", run.id, token, "initial", "sending")
    assert (await repository.inputs("alice", run.id))[0]["status"] == "withdrawn"


@pytest.mark.asyncio
async def test_status_cursor_matches_envelope(tmp_path):
    repository = RunRepository(tmp_path / "runs.db")
    run = await repository.create("alice", "environment", "initial", "build")
    token = await repository.claim("alice", run.id)
    assert token
    await repository.update("alice", run.id, token, state="running")
    status = (await repository.events("alice", run.id))[-1]
    assert status["payload"]["lastSeq"] == status["seq"]


@pytest.mark.asyncio
async def test_unknown_initial_submission_is_reconciled_without_resending(tmp_path):
    from frontend.server.intelligent_development_runs.runner import InputUnconfirmed
    from veadk.cli.codex_app_server import CodexAppServerSession

    repository = RunRepository(tmp_path / "runs.db")
    run = await repository.create("alice", "environment", "initial", "build")
    token = await repository.claim("alice", run.id)
    assert token
    await repository.input_status("alice", run.id, token, "initial", "sending")
    run = await repository.update(
        "alice", run.id, token, phase="coding", thread_id="thread"
    )
    codex = AsyncMock(spec=CodexAppServerSession)
    codex.find_input_turn.return_value = None
    runner = DevelopmentRunner(
        repository,
        resolve_session=AsyncMock(),
        workspace=lambda _: "/workspace",
        credentials=lambda: StudioCredentials("", ""),
        render_event=lambda *_: None,
    )
    with pytest.raises(InputUnconfirmed):
        await runner._coding(
            run,
            token,
            codex,
            cast(Any, SimpleNamespace(exact_secrets=())),
            cast(Any, SimpleNamespace()),
            "/workspace",
        )
    codex.find_input_turn.assert_awaited_once_with("initial")
    codex.stream_turn.assert_not_called()
    assert (await repository.inputs("alice", run.id))[0]["status"] == "sending"


@pytest.mark.asyncio
@pytest.mark.parametrize("definite_rejection", [False, True])
async def test_steer_rejection_and_unknown_delivery_never_repeat_in_same_turn(
    tmp_path, definite_rejection
):
    import asyncio
    from contextlib import suppress
    from veadk.cli.codex_app_server import (
        CodexAppServerRequestError,
        CodexAppServerSession,
    )

    repository = RunRepository(tmp_path / "runs.db")
    run = await repository.create("alice", "environment", "initial", "build")
    token = await repository.claim("alice", run.id)
    assert token
    await repository.input_status(
        "alice", run.id, token, "initial", "delivered", turn_id="t"
    )
    await repository.checkpoint("alice", run.id, token, accepted_revision=1)
    await repository.add_input("alice", run.id, "steer", "change")
    run = await repository.update(
        "alice", run.id, token, phase="coding", state="running", turn_id="t"
    )
    codex = AsyncMock(spec=CodexAppServerSession)
    codex.refresh_endpoint = lambda _: None
    codex.steer_turn.side_effect = (
        CodexAppServerRequestError({"code": -32600, "message": "turn ended"})
        if definite_rejection
        else TimeoutError()
    )
    reconciled = asyncio.Event()

    async def find(client):
        reconciled.set()
        return None

    codex.find_input_turn.side_effect = find
    runner = DevelopmentRunner(
        repository,
        resolve_session=AsyncMock(
            return_value=SimpleNamespace(endpoint="https://sandbox")
        ),
        workspace=lambda _: "/workspace",
        credentials=lambda: StudioCredentials("", ""),
        render_event=lambda *_: None,
    )
    control = asyncio.create_task(runner._control(run, token, codex))
    try:

        async def settled():
            while True:
                current = await repository.get("alice", run.id)
                if current.checkpoint.get("steer_wait_turn") or reconciled.is_set():
                    return current
                await asyncio.sleep(0.01)

        current = await asyncio.wait_for(settled(), 4)
        codex.steer_turn.assert_awaited_once_with("change", "t", "steer")
        inputs = await repository.inputs("alice", run.id)
        assert inputs[1]["status"] == ("pending" if definite_rejection else "sending")
        assert current.checkpoint["accepted_revision"] == 1
    finally:
        control.cancel()
        with suppress(asyncio.CancelledError):
            await control
