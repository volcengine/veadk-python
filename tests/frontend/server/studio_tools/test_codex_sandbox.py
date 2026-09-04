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

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest

from frontend.server.environments.session_mounts import SessionEnvironmentMount
from frontend.server.studio_tools.codex_sandbox import (
    CodexSandboxDelegate,
    _bounded_progress_event,
    _bounded_result_message,
    register_codex_sandbox_tool,
)
from frontend.server.studio_tools.registry import (
    StudioToolExecutionContext,
    StudioToolExecutionError,
    StudioToolRegistry,
    StudioToolRuntimeError,
)
from frontend.server.studio_tools.sandbox_shell import SandboxExecutionTarget
from veadk.cli.codex_app_server import (
    CodexAppServerEvent,
    CodexAppServerTransportError,
    CodexPermissionSettings,
)


def _mount(*, base_environment: str = "codex-sandbox") -> SessionEnvironmentMount:
    return SessionEnvironmentMount(
        environment_id="e" * 32,
        environment_version_id="version-1",
        image="registry.example/anr-review:v1",
        provider="volcengine",
        region="cn-beijing",
        name="ANR Review",
        description="Review requirements with the ANR CLI.",
        manifest={
            "spec": {
                "baseEnvironment": base_environment,
                "capabilities": ["review", "anr-cli"],
            }
        },
        tool_id="tool-1",
        tool_status="ready",
    )


def _context(
    mount: SessionEnvironmentMount,
    progress: list[dict[str, Any]],
) -> StudioToolExecutionContext:
    async def report_progress(event: dict[str, Any]) -> None:
        progress.append(event)

    return StudioToolExecutionContext(
        runtime_id="runtime-1",
        app_name="agent",
        user_id="user-1",
        session_id="session-1",
        run_id="run-1",
        scope_id="scope-1",
        catalog_revision="revision-1",
        owner_id="owner-1",
        environment_mount=mount,
        environment_mounts=(mount,),
        tool_request_id="request-1",
        report_progress=report_progress,
    )


def test_registered_delegate_uses_the_long_running_tool_timeout_limit() -> None:
    registry = StudioToolRegistry()
    register_codex_sandbox_tool(
        registry,
        mounts=object(),  # type: ignore[arg-type]
        delegate=object(),  # type: ignore[arg-type]
    )

    [manifest] = registry.snapshot(["delegate_to_codex_sandbox"]).manifests()

    assert manifest["timeout_ms"] == 30 * 60 * 1_000


def test_result_message_keeps_complete_prd_within_32k_limit() -> None:
    message = "产品需求文档\n" + "完整正文" * 4_000

    assert _bounded_result_message(message) == message


def test_result_message_preserves_start_and_marks_oversized_content() -> None:
    message = "PRD 开头\n" + "x" * 40_000 + "\nPRD 结尾"

    bounded = _bounded_result_message(message)

    assert bounded.startswith("PRD 开头\n")
    assert "PRD 结尾" not in bounded
    assert bounded.endswith("…内容过长，已截断")


def test_result_message_respects_utf8_channel_budget() -> None:
    bounded = _bounded_result_message("😀" * 32_768)

    assert len(bounded.encode("utf-8")) <= 96 * 1024
    assert bounded.startswith("😀" * 1_000)
    assert bounded.endswith("…内容过长，已截断")


@pytest.mark.asyncio
async def test_delegate_rejects_a_duplicate_call_while_the_same_session_is_busy() -> (
    None
):
    mount = _mount()
    started = asyncio.Event()
    release = asyncio.Event()
    turns: list[str] = []

    class Targets:
        async def resolve(
            self,
            selected: SessionEnvironmentMount,
            context: StudioToolExecutionContext,
        ) -> SandboxExecutionTarget:
            del selected, context
            return SandboxExecutionTarget(
                endpoint="https://sandbox.example",
                session_id="sandbox-1",
                tool_id="tool-1",
            )

    class Connection:
        thread_id = "codex-thread-1"

        async def connect(self) -> None:
            return None

        async def stream_turn(
            self,
            prompt: str,
            skill_ids: tuple[str, ...] = (),
            *,
            permissions: CodexPermissionSettings | None = None,
            timeout_seconds: float | None = None,
            output_schema: dict[str, object] | None = None,
        ) -> AsyncIterator[CodexAppServerEvent]:
            del skill_ids, permissions, timeout_seconds, output_schema
            turns.append(prompt)
            started.set()
            await release.wait()
            yield CodexAppServerEvent(kind="text", text="done")

        async def close(self) -> None:
            return None

    delegate = CodexSandboxDelegate(
        Targets(),
        connection_factory=lambda _: Connection(),
    )
    first = asyncio.create_task(delegate.execute(mount, "first", _context(mount, [])))
    await asyncio.wait_for(started.wait(), timeout=1)

    try:
        with pytest.raises(StudioToolRuntimeError, match="正忙"):
            await asyncio.wait_for(
                delegate.execute(mount, "duplicate", _context(mount, [])),
                timeout=1,
            )
    finally:
        release.set()
    result = await first
    assert result["message"] == "done"
    assert len(turns) == 1


@pytest.mark.asyncio
async def test_delegate_streams_codex_app_server_events_and_returns_final_text() -> (
    None
):
    mount = _mount()
    progress: list[dict[str, Any]] = []
    prompts: list[tuple[str, CodexPermissionSettings | None, float | None]] = []

    class Targets:
        async def resolve(
            self,
            selected: SessionEnvironmentMount,
            context: StudioToolExecutionContext,
        ) -> SandboxExecutionTarget:
            assert selected is mount
            assert context.session_id == "session-1"
            return SandboxExecutionTarget(
                endpoint="https://sandbox.example?Authorization=private",
                session_id="sandbox-1",
                tool_id="tool-1",
            )

    class Connection:
        thread_id = "codex-thread-1"

        async def connect(self) -> None:
            return None

        async def stream_turn(
            self,
            prompt: str,
            skill_ids: tuple[str, ...] = (),
            *,
            permissions: CodexPermissionSettings | None = None,
            timeout_seconds: float | None = None,
            output_schema: dict[str, object] | None = None,
        ) -> AsyncIterator[CodexAppServerEvent]:
            del skill_ids, output_schema
            prompts.append((prompt, permissions, timeout_seconds))
            yield CodexAppServerEvent(
                kind="thinking",
                item_id="reasoning-1",
                status="running",
                text="Inspecting the repository",
            )
            yield CodexAppServerEvent(
                kind="tool",
                item_id="command-1",
                status="done",
                name="运行命令",
                arguments={"command": "anr review --help"},
                response={"exitCode": 0, "output": "usage"},
            )
            yield CodexAppServerEvent(kind="text", text="Review complete.")
            yield CodexAppServerEvent(
                kind="text",
                item_id="assistant-message-duplicate",
                text="Review complete.",
            )
            yield CodexAppServerEvent(
                kind="assistant_final",
                item_id="assistant-final-1",
                text="Final review complete.",
            )

        async def close(self) -> None:
            raise AssertionError("healthy connections should be reused")

    delegate = CodexSandboxDelegate(
        Targets(), connection_factory=lambda _: Connection()
    )

    result = await delegate.execute(
        mount,
        "Review the requirements and return actionable findings.",
        _context(mount, progress),
    )

    activity = result.pop("codex_activity")
    assert result == {
        "ok": True,
        "environment_id": "e" * 32,
        "agent_session_id": "session-1",
        "sandbox_session_id": "sandbox-1",
        "thread_id": "codex-thread-1",
        "message": "Final review complete.",
    }
    assert activity == {
        "title": "ANR Review",
        "agent_session_id": "session-1",
        "sandbox_session_id": "sandbox-1",
        "thread_id": "codex-thread-1",
        "events": [item["event"] for item in progress],
    }
    prompt, permissions, timeout_seconds = prompts[0]
    assert "ANR Review" in prompt
    assert "review, anr-cli" in prompt
    assert "anr review" not in prompt
    assert "Batch related non-destructive shell checks" in prompt
    assert "avoid repeating successful checks" in prompt
    assert "complete user-visible deliverable" in prompt
    assert "Do not only save it to a Sandbox-local file" in prompt
    assert "Return exactly one final answer" in prompt
    assert "complete but concise enough" in prompt
    assert "Review the requirements" in prompt
    assert permissions == CodexPermissionSettings(
        approval_policy="never",
        approvals_reviewer="auto_review",
        sandbox_mode="danger-full-access",
        network_access=True,
    )
    assert timeout_seconds is None
    assert progress == [
        {
            "kind": "codex",
            "title": "ANR Review",
            "event": {
                "id": "turn:request-1",
                "kind": "status",
                "status": "running",
                "text": "Codex Sandbox 已接收任务",
                "agentSessionId": "session-1",
                "sandboxSessionId": "sandbox-1",
                "threadId": "codex-thread-1",
            },
        },
        {
            "kind": "codex",
            "title": "ANR Review",
            "event": {
                "id": "reasoning-1",
                "kind": "thinking",
                "status": "running",
                "text": "Inspecting the repository",
            },
        },
        {
            "kind": "codex",
            "title": "ANR Review",
            "event": {
                "id": "command-1",
                "kind": "tool",
                "status": "done",
                "name": "运行命令",
                "arguments": {"command": "anr review --help"},
                "response": {"exitCode": 0, "output": "usage"},
            },
        },
        {
            "kind": "codex",
            "title": "ANR Review",
            "event": {
                "id": "turn:request-1",
                "kind": "status",
                "status": "completed",
                "text": "Codex Sandbox 已完成任务",
                "agentSessionId": "session-1",
                "sandboxSessionId": "sandbox-1",
                "threadId": "codex-thread-1",
            },
        },
    ]


@pytest.mark.asyncio
async def test_delegate_keeps_persisted_activity_compact_for_large_outputs() -> None:
    mount = _mount()
    progress: list[dict[str, Any]] = []

    class Targets:
        async def resolve(
            self,
            selected: SessionEnvironmentMount,
            context: StudioToolExecutionContext,
        ) -> SandboxExecutionTarget:
            del selected, context
            return SandboxExecutionTarget(
                endpoint="https://sandbox.example?Authorization=private",
                session_id="sandbox-1",
            )

    class Connection:
        thread_id = "codex-thread-1"

        async def connect(self) -> None:
            return None

        async def stream_turn(
            self,
            prompt: str,
            skill_ids: tuple[str, ...] = (),
            *,
            permissions: CodexPermissionSettings | None = None,
            timeout_seconds: float | None = None,
            output_schema: dict[str, object] | None = None,
        ) -> AsyncIterator[CodexAppServerEvent]:
            del prompt, skill_ids, permissions, timeout_seconds, output_schema
            yield CodexAppServerEvent(
                kind="tool",
                item_id="large-command",
                status="done",
                name="运行命令",
                arguments={"command": "x" * 100_000},
                response={"output": "y" * 100_000},
            )
            yield CodexAppServerEvent(kind="text", text="draft" * 20_000)
            yield CodexAppServerEvent(
                kind="assistant_final",
                item_id="assistant-final-1",
                text="最终结果",
            )

        async def close(self) -> None:
            return None

    delegate = CodexSandboxDelegate(
        Targets(), connection_factory=lambda _: Connection()
    )

    result = await delegate.execute(
        mount, "Write the result", _context(mount, progress)
    )

    assert result["message"] == "最终结果"
    assert len(json.dumps(result["codex_activity"], ensure_ascii=False)) < 20_000


@pytest.mark.asyncio
async def test_registered_delegate_rejects_non_codex_environment() -> None:
    mount = _mount(base_environment="aio-sandbox")

    class Mounts:
        @staticmethod
        def get(
            context: StudioToolExecutionContext,
            environment_id: str = "",
        ) -> SessionEnvironmentMount:
            del context, environment_id
            return mount

    class Targets:
        async def resolve(
            self,
            selected: SessionEnvironmentMount,
            context: StudioToolExecutionContext,
        ) -> SandboxExecutionTarget:
            raise AssertionError((selected, context))

    registry = StudioToolRegistry()
    register_codex_sandbox_tool(
        registry,
        mounts=Mounts(),  # type: ignore[arg-type]
        delegate=CodexSandboxDelegate(Targets()),
    )

    with pytest.raises(StudioToolExecutionError, match="不是 Codex Sandbox"):
        await registry.execute(
            name="delegate_to_codex_sandbox",
            executor_revision="codex-app-server-v1",
            arguments={
                "environment_id": "e" * 32,
                "task": "Review this project.",
            },
            context=_context(mount, []),
        )


@pytest.mark.asyncio
async def test_registered_delegate_uses_the_context_mount() -> None:
    mount = _mount()
    progress: list[dict[str, Any]] = []

    class Mounts:
        @staticmethod
        def get(
            context: StudioToolExecutionContext,
            environment_id: str = "",
        ) -> SessionEnvironmentMount:
            assert environment_id == mount.environment_id
            assert context.environment_mount is mount
            return mount

    class Targets:
        async def resolve(
            self,
            selected: SessionEnvironmentMount,
            context: StudioToolExecutionContext,
        ) -> SandboxExecutionTarget:
            del selected, context
            return SandboxExecutionTarget(
                endpoint="https://sandbox.example?Authorization=private",
                session_id="sandbox-1",
            )

    class Connection:
        thread_id = "thread-1"

        async def connect(self) -> None:
            return None

        async def stream_turn(
            self,
            prompt: str,
            skill_ids: tuple[str, ...] = (),
            *,
            permissions: CodexPermissionSettings | None = None,
            timeout_seconds: float | None = None,
            output_schema: dict[str, object] | None = None,
        ) -> AsyncIterator[CodexAppServerEvent]:
            del prompt, skill_ids, permissions, timeout_seconds, output_schema
            yield CodexAppServerEvent(kind="text", text="done")

        async def close(self) -> None:
            return None

    registry = StudioToolRegistry()
    register_codex_sandbox_tool(
        registry,
        mounts=Mounts(),  # type: ignore[arg-type]
        delegate=CodexSandboxDelegate(
            Targets(),
            connection_factory=lambda _: Connection(),
        ),
    )

    result = await registry.execute(
        name="delegate_to_codex_sandbox",
        executor_revision="codex-app-server-v1",
        arguments={"environment_id": mount.environment_id, "task": "Do the work"},
        context=_context(mount, progress),
    )

    assert result["message"] == "done"


@pytest.mark.asyncio
async def test_delegate_retries_only_initial_app_server_connection(
    caplog: pytest.LogCaptureFixture,
) -> None:
    mount = _mount()
    progress: list[dict[str, Any]] = []
    sleeps: list[float] = []
    created: list[Connection] = []

    class Targets:
        async def resolve(
            self,
            selected: SessionEnvironmentMount,
            context: StudioToolExecutionContext,
        ) -> SandboxExecutionTarget:
            del selected, context
            return SandboxExecutionTarget(
                endpoint="https://sandbox.example?Authorization=private-token",
                session_id="sandbox-1",
            )

    class Connection:
        thread_id = ""

        def __init__(self, attempt: int) -> None:
            self.attempt = attempt
            self.closed = False

        async def connect(self) -> None:
            if self.attempt < 3:
                raise CodexAppServerTransportError(
                    "handshake failed at https://sandbox.example?Authorization=private-token"
                )
            self.thread_id = "thread-after-retry"

        async def stream_turn(
            self,
            prompt: str,
            skill_ids: tuple[str, ...] = (),
            *,
            permissions: CodexPermissionSettings | None = None,
            timeout_seconds: float | None = None,
            output_schema: dict[str, object] | None = None,
        ) -> AsyncIterator[CodexAppServerEvent]:
            del prompt, skill_ids, permissions, timeout_seconds, output_schema
            yield CodexAppServerEvent(kind="text", text="ready")

        async def close(self) -> None:
            self.closed = True

    def connection_factory(endpoint: str) -> Connection:
        assert endpoint.endswith("Authorization=private-token")
        connection = Connection(len(created) + 1)
        created.append(connection)
        return connection

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    delegate = CodexSandboxDelegate(
        Targets(),
        connection_factory=connection_factory,
        sleep=sleep,
    )

    result = await delegate.execute(
        mount,
        "Review the project",
        _context(mount, progress),
    )

    assert result["message"] == "ready"
    assert sleeps == [1.0, 2.0]
    assert [connection.closed for connection in created] == [True, True, False]
    assert "private-token" not in caplog.text
    retry_statuses = [
        item["event"]["text"]
        for item in progress
        if "准备第" in str(item["event"].get("text"))
    ]
    assert retry_statuses == [
        "Codex Sandbox 正在启动，准备第 2/4 次连接",
        "Codex Sandbox 正在启动，准备第 3/4 次连接",
    ]


@pytest.mark.asyncio
async def test_delegate_waits_for_app_server_readiness_before_connecting() -> None:
    mount = _mount()
    progress: list[dict[str, Any]] = []
    readiness = iter((False, False, True))
    sleeps: list[float] = []
    connect_calls = 0

    class Targets:
        async def resolve(
            self,
            selected: SessionEnvironmentMount,
            context: StudioToolExecutionContext,
        ) -> SandboxExecutionTarget:
            del selected, context
            return SandboxExecutionTarget(
                endpoint="https://sandbox.example?Authorization=private",
                session_id="sandbox-1",
            )

    class Connection:
        thread_id = "thread-ready"

        async def connect(self) -> None:
            nonlocal connect_calls
            connect_calls += 1

        async def stream_turn(
            self,
            prompt: str,
            skill_ids: tuple[str, ...] = (),
            *,
            permissions: CodexPermissionSettings | None = None,
            timeout_seconds: float | None = None,
            output_schema: dict[str, object] | None = None,
        ) -> AsyncIterator[CodexAppServerEvent]:
            del prompt, skill_ids, permissions, timeout_seconds, output_schema
            yield CodexAppServerEvent(kind="text", text="ready")

        async def close(self) -> None:
            return None

    async def readiness_probe(target: SandboxExecutionTarget) -> bool:
        assert "private" in target.endpoint
        return next(readiness)

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    delegate = CodexSandboxDelegate(
        Targets(),
        connection_factory=lambda _: Connection(),
        readiness_probe=readiness_probe,
        sleep=sleep,
    )

    result = await delegate.execute(
        mount,
        "Review the project",
        _context(mount, progress),
    )

    assert result["message"] == "ready"
    assert sleeps == [1.0, 2.0]
    assert connect_calls == 1


@pytest.mark.asyncio
async def test_delegate_does_not_replay_a_turn_after_transport_failure() -> None:
    mount = _mount()
    progress: list[dict[str, Any]] = []
    stream_calls = 0

    class Targets:
        async def resolve(
            self,
            selected: SessionEnvironmentMount,
            context: StudioToolExecutionContext,
        ) -> SandboxExecutionTarget:
            del selected, context
            return SandboxExecutionTarget(
                endpoint="https://sandbox.example?Authorization=private",
                session_id="sandbox-1",
            )

    class Connection:
        thread_id = "thread-1"

        async def connect(self) -> None:
            return None

        async def stream_turn(
            self,
            prompt: str,
            skill_ids: tuple[str, ...] = (),
            *,
            permissions: CodexPermissionSettings | None = None,
            timeout_seconds: float | None = None,
            output_schema: dict[str, object] | None = None,
        ) -> AsyncIterator[CodexAppServerEvent]:
            nonlocal stream_calls
            del prompt, skill_ids, permissions, timeout_seconds, output_schema
            stream_calls += 1
            yield CodexAppServerEvent(
                kind="tool",
                item_id="command-1",
                status="running",
                name="运行命令",
            )
            raise CodexAppServerTransportError("connection closed")

        async def close(self) -> None:
            return None

    delegate = CodexSandboxDelegate(
        Targets(),
        connection_factory=lambda _: Connection(),
        sleep=lambda _: _completed_sleep(),
    )

    with pytest.raises(StudioToolRuntimeError, match="连接中断") as error_info:
        await delegate.execute(
            mount,
            "Review the project",
            _context(mount, progress),
        )

    assert stream_calls == 1
    content = error_info.value.content
    assert content["ok"] is False
    activity = content["codex_activity"]
    assert activity["agent_session_id"] == "session-1"
    assert activity["sandbox_session_id"] == "sandbox-1"
    assert activity["thread_id"] == "thread-1"
    assert activity["events"][-1]["status"] == "failed"


async def _completed_sleep() -> None:
    return None


def test_progress_payload_is_redacted_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "server-secret-value")

    event = _bounded_progress_event(
        {
            "id": "command-1",
            "kind": "tool",
            "status": "done",
            "arguments": {
                "command": "curl -H 'Authorization: Bearer private-token' URL"
            },
            "response": {
                "api_key": "private-api-key",
                "output": "server-secret-value\n" + "x" * 100_000,
            },
        }
    )

    encoded = json.dumps(event, ensure_ascii=False).encode("utf-8")
    assert len(encoded) <= 64 * 1024
    assert b"server-secret-value" not in encoded
    assert b"private-token" not in encoded
    assert b"private-api-key" not in encoded
    assert event["response"]["api_key"] == "***"
    assert len(event["response"]["output"]) <= 16_000
