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

"""Delivery-tool lifecycle with a real SQLite store and controlled remote boundaries."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frontend.server.intelligent_development import DeliveryReference, StudioCredentials
from frontend.server.intelligent_development_runs import runner as runner_module
from frontend.server.intelligent_development_runs.repository import (
    RunLeaseLost,
    RunNotFound,
    RunRepository,
)
from frontend.server.intelligent_development_runs.runner import DevelopmentRunner
from frontend.server.intelligent_development_task import (
    BUILD_RESULT_TOOL,
    parse_build_result,
)
from veadk.cli.codex_app_server import CodexAppServerEvent


def result(revision=1):
    return {
        "inputRevision": revision,
        "schemaVersion": "1",
        "status": "verified",
        "summary": "Math tutor ready",
        "intentSummary": "Build a primary-school math tutor",
        "runtimeName": "idv-math-tutor",
        "attemptCount": 1,
        "gates": {
            gate: True
            for gate in BUILD_RESULT_TOOL["inputSchema"]["properties"]["gates"][
                "required"
            ]
        },
        "acceptanceCriteria": [
            "Explain addition step by step",
            "Keep responses age appropriate",
        ],
    }


async def setup_run(tmp_path):
    repo = RunRepository(tmp_path / "runs.db")
    run = await repo.create(
        "alice",
        "sandbox",
        "request-1",
        "Build a primary-school math tutor",
        result_protocol="tool-v1",
    )
    token = await repo.claim("alice", run.id)
    await repo.update(
        "alice", run.id, token, thread_id="thread-1", turn_id="turn-1", phase="coding"
    )
    await repo.input_status(
        "alice", run.id, token, "request-1", "delivered", turn_id="turn-1"
    )
    run = await repo.checkpoint("alice", run.id, token, accepted_revision=1)
    runner = DevelopmentRunner(
        repo,
        resolve_session=AsyncMock(),
        workspace=lambda _: "/workspace",
        credentials=lambda: StudioCredentials("test-access", "test-secret"),
        render_event=lambda *_: None,
    )
    lease = SimpleNamespace(exact_secrets=())
    params = {
        "threadId": "thread-1",
        "turnId": "turn-1",
        "callId": "call-1",
        "tool": "submit_build_result",
        "namespace": None,
        "arguments": result(),
    }
    return repo, run, token, runner, lease, params


@pytest.mark.asyncio
async def test_invalid_metadata_can_be_corrected_and_durably_replayed(tmp_path):
    repo, run, token, runner, lease, params = await setup_run(tmp_path)
    params["arguments"]["acceptanceCriteria"] = []
    failed = await runner._submit_result("alice", run.id, token, params, lease)
    assert failed["success"] is False
    assert "acceptanceCriteria" in failed["contentItems"][0]["text"]
    assert await repo.result_for_turn("alice", run.id, token) is None
    params["arguments"] = result()
    accepted = await runner._submit_result("alice", run.id, token, params, lease)
    assert accepted["success"] is True
    runner.repository = RunRepository(repo.path)  # process/reply loss, same SQLite
    assert (
        await runner._submit_result("alice", run.id, token, params, lease) == accepted
    )
    saved = await runner.repository.result_for_turn("alice", run.id, token)
    assert saved["intent_summary"] == result()["intentSummary"]
    params["arguments"]["summary"] = "Different result on the same call"
    assert (await runner._submit_result("alice", run.id, token, params, lease))[
        "success"
    ] is False
    assert (await repo.result_for_turn("alice", run.id, token))[
        "summary"
    ] == "Math tutor ready"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "conflict",
    ["owner", "lease", "thread", "turn", "stop", "pending", "sending", "stale"],
)
async def test_results_are_bound_to_owner_lease_turn_and_input_revision(
    tmp_path, conflict
):
    repo, run, token, runner, lease, params = await setup_run(tmp_path)
    owner = "alice"
    if conflict == "owner":
        owner = "bob"
    if conflict == "lease":
        token = "lost-lease"
    if conflict in {"thread", "turn"}:
        params[conflict + "Id"] = "unrelated"
    if conflict == "stop":
        await repo.request_stop("alice", run.id)
    if conflict in {"pending", "sending", "stale"}:
        await repo.add_input("alice", run.id, "steer", "Also teach fractions")
        if conflict in {"sending", "stale"}:
            await repo.input_status(
                "alice",
                run.id,
                token,
                "steer",
                "sending" if conflict == "sending" else "delivered",
                turn_id="turn-1",
            )
        if conflict == "stale":
            await repo.checkpoint("alice", run.id, token, accepted_revision=2)
    if conflict in {"owner", "lease"}:
        with pytest.raises(RunNotFound if conflict == "owner" else RunLeaseLost):
            await runner._submit_result(owner, run.id, token, params, lease)
    else:
        assert (await runner._submit_result(owner, run.id, token, params, lease))[
            "success"
        ] is False


@pytest.mark.asyncio
async def test_steer_invalidates_receipt_and_fences_the_artifact_event(tmp_path):
    repo, run, token, runner, lease, params = await setup_run(tmp_path)
    assert (await runner._submit_result("alice", run.id, token, params, lease))[
        "success"
    ] is True
    await repo.checkpoint(
        "alice",
        run.id,
        token,
        completion_revision=1,
        version={"verified": True, "agentName": "math_tutor"},
    )
    await repo.add_input("alice", run.id, "steer", "Also teach fractions")
    assert not await repo.finish("alice", run.id, token, 1)
    assert await repo.result_for_turn("alice", run.id, token) is None
    assert (await runner._submit_result("alice", run.id, token, params, lease))[
        "success"
    ] is False
    assert not any(
        e["type"].startswith("development.") for e in await repo.events("alice", run.id)
    )
    await repo.input_status(
        "alice", run.id, token, "steer", "delivered", turn_id="turn-1"
    )
    await repo.checkpoint("alice", run.id, token, accepted_revision=2)
    params.update(callId="call-2", arguments=result(2))
    assert (await runner._submit_result("alice", run.id, token, params, lease))[
        "success"
    ] is True
    await repo.checkpoint("alice", run.id, token, completion_revision=2)
    assert await repo.finish("alice", run.id, token, 2)
    assert not await repo.finish("alice", run.id, token, 2)
    assert (
        len(
            [
                e
                for e in await repo.events("alice", run.id)
                if e["type"] == "development.succeeded"
            ]
        )
        == 1
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.update(attemptCount=True),
        lambda r: r.update(runtimeName="wrong-name"),
        lambda r: r["gates"].update({"ak-build": False}),
        lambda r: r.update(ownerId="bob"),
        lambda r: r.update(status="answered"),
        lambda r: r.update(summary=" "),
    ],
)
def test_tool_contract_rejects_bad_types_and_false_verified_claims(mutation):
    value = result()
    mutation(value)
    with pytest.raises(ValueError):
        parse_build_result(value)


@pytest.mark.asyncio
async def test_reporting_recovery_is_bounded_read_only_and_keeps_business_goal(
    tmp_path,
):
    repo, run, token, runner, lease, params = await setup_run(tmp_path)
    assert await runner._continue_turn(run, token, report_only=True)
    run = await repo.get("alice", run.id)
    assert run.phase == "reporting"
    assert not await runner._continue_turn(run, token, report_only=True)
    seen = []

    class Codex:
        thread_id = "thread-1"
        active_turn_id = "report-turn"

        async def stream_turn(self, prompt, **options):
            seen.append((prompt, options))
            yield CodexAppServerEvent(kind="turn_started", turn_id="report-turn")
            yield CodexAppServerEvent(
                kind="turn_completed",
                turn_id="report-turn",
                status="completed",
                response={"durationMs": 23},
            )

    await runner._coding(run, token, Codex(), lease, SimpleNamespace(), "/workspace")
    prompt, options = seen[0]
    assert "Build a primary-school math tutor" in prompt
    assert "Only its structured delivery metadata is missing" in prompt
    assert (
        "Use the preinstalled veadk-agent-development Skill for this task" not in prompt
    )
    assert "Do not resume development" in prompt
    assert options["permissions"].sandbox_mode == "read-only"
    assert options["permissions"].network_access is False
    assert (await repo.get("alice", run.id)).phase == "outcome_read"


@pytest.mark.asyncio
@pytest.mark.parametrize("omit_first_result", [False, True])
async def test_complete_build_publishes_once_without_a_file_or_development_replay(
    tmp_path, monkeypatch, omit_first_result
):
    repo = RunRepository(tmp_path / "runs.db")
    run = await repo.create(
        "alice",
        "sandbox",
        "request-1",
        "Build a primary-school math tutor",
        result_protocol="tool-v1",
    )
    token = await repo.claim("alice", run.id)
    lease = SimpleNamespace(
        root="/task",
        credential_path="/task/credentials.json",
        launcher_path="/task/launcher",
        exact_secrets=(),
        cleanup=AsyncMock(),
    )
    transport = SimpleNamespace(
        download=AsyncMock(
            return_value=b'{"accessKeyId":"test-access","secretAccessKey":"test-secret"}'
        )
    )
    monkeypatch.setattr(runner_module, "SandboxRemoteTransport", lambda _: transport)
    monkeypatch.setattr(
        runner_module, "create_credential_lease", AsyncMock(return_value=lease)
    )
    monkeypatch.setattr(runner_module, "invalidate_current_delivery", AsyncMock())
    file_reader = AsyncMock(
        side_effect=AssertionError("new protocol must not read a result filename")
    )
    monkeypatch.setattr(runner_module, "read_completion_contract", file_reader)
    delivery = DeliveryReference(
        "a" * 64,
        1024,
        "b" * 64,
        "sandbox",
        "math_tutor",
        "agent.py",
        3,
        "2026-09-16T00:00:00Z",
        ("ak-build",),
        True,
        True,
        "Passed",
    )
    publish = AsyncMock(return_value=delivery)
    monkeypatch.setattr(
        runner_module, "DeliveryPublisher", lambda _: SimpleNamespace(publish=publish)
    )

    class Codex:
        thread_id = "thread-1"
        active = False
        active_turn_id = ""
        turns = []

        async def connect(self):
            assert self.dynamic_tools[0]["name"] == "submit_build_result"

        async def attach_thread(self, thread_id, **kwargs):
            assert thread_id == self.thread_id

        async def close(self):
            pass

        async def stream_turn(self, prompt, **options):
            self.turns.append(prompt)
            turn_id = f"turn-{len(self.turns)}"
            self.active_turn_id = turn_id
            yield CodexAppServerEvent(kind="turn_started", turn_id=turn_id)
            if not (omit_first_result and len(self.turns) == 1):
                params = {
                    "threadId": self.thread_id,
                    "turnId": turn_id,
                    "callId": "call-1",
                    "tool": "submit_build_result",
                    "namespace": None,
                    "arguments": result(),
                }
                assert (await self.dynamic_tool_handler(params))["success"]
                assert (await self.dynamic_tool_handler(params))[
                    "success"
                ]  # lost reply
            yield CodexAppServerEvent(
                kind="text",
                turn_id=turn_id,
                item_id="answer",
                text="Math tutor complete",
            )
            yield CodexAppServerEvent(
                kind="turn_completed",
                turn_id=turn_id,
                status="completed",
                response={"durationMs": 100},
            )

    codex = Codex()
    runner = DevelopmentRunner(
        repo,
        resolve_session=AsyncMock(
            return_value=SimpleNamespace(
                created_by="alice", endpoint="https://sandbox", expire_at=""
            )
        ),
        workspace=lambda _: "/workspace",
        credentials=lambda: StudioCredentials("test-access", "test-secret"),
        render_event=lambda e, _: ("delta", {"text": e.text})
        if e.kind == "text"
        else None,
        codex_factory=lambda _: codex,
    )
    await runner._attempt(run, token)
    latest = await repo.get("alice", run.id)
    assert latest.state == "succeeded"
    assert len(codex.turns) == (2 if omit_first_result else 1)
    if omit_first_result:
        assert "Only its structured delivery metadata is missing" in codex.turns[1]
        assert (
            "Use the preinstalled veadk-agent-development Skill for this task"
            not in codex.turns[1]
        )
    file_reader.assert_not_called()
    publish.assert_awaited_once()
    assert (
        publish.call_args.kwargs["completion"].intent_summary
        == "Build a primary-school math tutor"
    )
    events = await repo.events("alice", run.id)
    cards = [e for e in events if e["type"] == "development.succeeded"]
    assert len(cards) == 1
    states = [
        e["payload"]["statusMessage"] for e in events if e["type"] == "run.status"
    ]
    assert "正在整理产物" in states and "正在保存版本" in states
    turn_events = [
        e
        for e in events
        if e["type"] == "run.turn" and e["payload"]["status"] == "completed"
    ]
    assert turn_events and all(e["seq"] < cards[0]["seq"] for e in turn_events)
    lease.cleanup.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["failed", "interrupted"])
async def test_submitted_result_does_not_publish_a_failed_or_interrupted_turn(
    tmp_path, status
):
    from veadk.cli.codex_app_server import CodexAppServerError
    from frontend.server.intelligent_development_runs.runner import NativeTurnFailed

    repo, run, token, runner, lease, params = await setup_run(tmp_path)
    run = await repo.checkpoint("alice", run.id, token, continuation_count=2)

    class Codex:
        thread_id = "thread-1"
        active_turn_id = "turn-1"

        async def read_turn(self, _):
            return {"id": "turn-1", "status": status}

        async def stream_turn(self, *_args, **_options):
            yield CodexAppServerEvent(kind="turn_started", turn_id="turn-1")
            assert (await runner._submit_result("alice", run.id, token, params, lease))[
                "success"
            ]
            yield CodexAppServerEvent(
                kind="turn_completed",
                turn_id="turn-1",
                status=status,
                response={"durationMs": 87},
            )
            raise CodexAppServerError("Native terminal failure")

    with pytest.raises(NativeTurnFailed):
        await runner._coding(
            run, token, Codex(), lease, SimpleNamespace(), "/workspace"
        )
    current = await repo.get("alice", run.id)
    assert current.phase == "coding" and not current.checkpoint.get("completion")
    events = await repo.events("alice", run.id)
    assert not any(event["type"].startswith("development.") for event in events)
    assert any(
        event["type"] == "run.turn"
        and event["payload"]["status"] == status
        and event["payload"]["durationMs"] == 87
        for event in events
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit_stop", [False, True])
async def test_reporting_obeys_deadline_and_user_stop_without_steering(
    tmp_path, explicit_stop
):
    import asyncio
    from contextlib import suppress

    repo, run, token, runner, lease, params = await setup_run(tmp_path)
    await repo.update("alice", run.id, token, phase="reporting")
    run = await repo.checkpoint(
        "alice", run.id, token, report_deadline=repo.clock() - 1
    )
    await repo.add_input("alice", run.id, "steer", "Also teach fractions")
    if explicit_stop:
        await repo.request_stop("alice", run.id)
    interrupted = asyncio.Event()

    async def interrupt(turn_id):
        assert turn_id == "turn-1"
        interrupted.set()

    codex = SimpleNamespace(
        active=True,
        interrupt_turn=AsyncMock(side_effect=interrupt),
        steer_turn=AsyncMock(),
    )
    task = asyncio.create_task(runner._control(run, token, codex))
    try:
        await asyncio.wait_for(interrupted.wait(), 2)
        codex.steer_turn.assert_not_called()
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_saved_results_are_redacted_before_storage_and_deleted_with_the_run(
    tmp_path,
):
    repo, run, token, runner, lease, params = await setup_run(tmp_path)
    lease.exact_secrets = ("private-value-for-test",)
    params["arguments"]["summary"] = "Completed private-value-for-test"
    assert (await runner._submit_result("alice", run.id, token, params, lease))[
        "success"
    ]
    assert (await repo.result_for_turn("alice", run.id, token))[
        "summary"
    ] == "Completed ***"
    await repo.request_stop("alice", run.id)
    assert not await repo.finish("alice", run.id, token, 1)
    await repo.update("alice", run.id, token, state="cancelled")
    await repo.delete("alice", run.id)
    import sqlite3

    with sqlite3.connect(repo.path) as db:
        assert db.execute("SELECT count(*) FROM run_results").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_new_input_after_failed_reporting_starts_a_development_cycle(tmp_path):
    repo, run, token, runner, lease, params = await setup_run(tmp_path)
    await runner._continue_turn(run, token, report_only=True)
    await repo.update(
        "alice",
        run.id,
        token,
        phase="reporting",
        turn_id="report-turn",
        state="waiting_user",
    )
    await repo.add_input("alice", run.id, "steer", "Also teach fractions")
    run = await repo.checkpoint("alice", run.id, token, continuation_sending=True)
    codex = SimpleNamespace(
        read_turn=AsyncMock(return_value={"id": "report-turn", "status": "failed"})
    )
    await runner._coding(run, token, codex, lease, SimpleNamespace(), "/workspace")
    current = await repo.get("alice", run.id)
    assert current.phase == "prepare" and current.turn_id == ""
    assert current.checkpoint["report_only"] is False
    assert current.checkpoint["continuation"] is None
    assert (await repo.inputs("alice", run.id))[-1]["status"] == "pending"
