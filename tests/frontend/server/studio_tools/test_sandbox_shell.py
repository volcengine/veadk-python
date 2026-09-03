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

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from frontend.server.environments.session_mounts import SessionEnvironmentMount
from frontend.server.studio_tools.registry import (
    StudioToolExecutionContext,
    StudioToolExecutionError,
    StudioToolRegistry,
)
from frontend.server.studio_tools.sandbox_shell import (
    AgentkitEnvironmentSandboxResolver,
    SandboxExecutionTarget,
    SandboxResolutionError,
    _user_session_id,
    execute_in_sandbox,
    register_sandbox_shell_tool,
)


def _mount(image: str = "registry.example/environment:v1") -> SessionEnvironmentMount:
    return SessionEnvironmentMount(
        environment_id="e" * 32,
        environment_version_id="version-1",
        image=image,
        provider="volcengine",
        region="cn-beijing",
        name="AIO environment",
        description="Includes common CLIs",
        manifest={
            "apiVersion": "agentkit.studio/v1alpha1",
            "kind": "Environment",
            "metadata": {"id": "e" * 32, "name": "AIO environment"},
            "spec": {"capabilities": ["shell", "cli"]},
        },
        tool_id="tool-persisted",
        tool_status="ready",
    )


def _context(
    session_id: str = "session-1",
    *,
    mount: SessionEnvironmentMount | None = None,
    mounts: tuple[SessionEnvironmentMount, ...] = (),
) -> StudioToolExecutionContext:
    return StudioToolExecutionContext(
        runtime_id="runtime-1",
        app_name="app-1",
        user_id="user-1",
        session_id=session_id,
        run_id="run-1",
        scope_id=f"scope-{session_id}",
        catalog_revision="revision-1",
        owner_id="owner-1",
        environment_mount=mount,
        environment_mounts=mounts,
    )


@pytest.mark.asyncio
async def test_execute_in_sandbox_preserves_endpoint_auth_and_normalizes_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content
        captured["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "status": "completed",
                    "exit_code": 0,
                    "output": "hello\n",
                    "session_id": "private-shell-id",
                },
            },
        )

    real_client = httpx.AsyncClient

    def client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(
        "frontend.server.studio_tools.sandbox_shell.httpx.AsyncClient",
        client_factory,
    )

    result = await execute_in_sandbox(
        SandboxExecutionTarget(
            endpoint=(
                "https://sandbox.example/base?faasInstanceName=instance-1"
                "&Authorization=secret"
            ),
            session_id="sandbox-session-1",
            headers={"Authorization": "Bearer server-secret", "Host": "evil.test"},
        ),
        {"command": "printf hello", "cwd": "/workspace", "timeout_seconds": 7},
    )

    assert captured["url"] == (
        "https://sandbox.example/base/v1/shell/exec?"
        "faasInstanceName=instance-1&Authorization=secret"
    )
    assert json_body(captured["body"]) == {
        "id": "",
        "exec_dir": "/workspace",
        "command": "printf hello",
        "timeout": 7,
        "hard_timeout": 300,
        "strict": True,
    }
    assert captured["headers"]["authorization"] == "Bearer server-secret"
    assert captured["headers"]["host"] == "sandbox.example"
    assert result == {
        "ok": True,
        "running": False,
        "status": "completed",
        "exit_code": 0,
        "output": "hello\n",
        "output_truncated": False,
        "command_id": "private-shell-id",
    }


@pytest.mark.asyncio
async def test_execute_in_sandbox_returns_pollable_running_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[str, dict[str, Any]]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json_body(request.content)
        requests.append((request.url.path, body))
        if request.url.path.endswith("/exec"):
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "session_id": "shell-1",
                        "status": "running",
                        "output": None,
                        "exit_code": None,
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "session_id": "shell-1",
                    "status": "completed",
                    "output": "done\n",
                    "exit_code": 0,
                },
            },
        )

    real_client = httpx.AsyncClient

    def client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(
        "frontend.server.studio_tools.sandbox_shell.httpx.AsyncClient",
        client_factory,
    )
    target = SandboxExecutionTarget(
        endpoint="https://sandbox.example?Authorization=secret",
        session_id="sandbox-session-1",
    )

    running = await execute_in_sandbox(
        target,
        {
            "command": "sleep 3; echo done",
            "timeout_seconds": 1,
            "hard_timeout_seconds": 10,
        },
    )
    completed = await execute_in_sandbox(
        target,
        {"command_id": "shell-1", "timeout_seconds": 2},
    )

    assert running == {
        "ok": False,
        "running": True,
        "status": "running",
        "exit_code": None,
        "output": "",
        "output_truncated": False,
        "command_id": "shell-1",
    }
    assert completed["ok"] is True
    assert completed["output"] == "done\n"
    assert requests == [
        (
            "/v1/shell/exec",
            {
                "id": "",
                "exec_dir": "/home/gem",
                "command": "sleep 3; echo done",
                "timeout": 1,
                "hard_timeout": 10,
                "strict": True,
            },
        ),
        (
            "/v1/shell/wait",
            {"id": "shell-1", "seconds": 2, "max_wait_seconds": 2},
        ),
    ]


@pytest.mark.asyncio
async def test_registered_tool_requires_a_session_mount() -> None:
    class Mounts:
        @staticmethod
        def get(
            context: StudioToolExecutionContext, environment_id: str = ""
        ) -> SessionEnvironmentMount:
            del context
            del environment_id
            raise ValueError("当前会话尚未挂载可执行环境。")

    class Targets:
        async def resolve(
            self,
            mount: SessionEnvironmentMount,
            context: StudioToolExecutionContext,
        ) -> SandboxExecutionTarget:
            raise AssertionError((mount, context))

    registry = StudioToolRegistry()
    register_sandbox_shell_tool(
        registry,
        mounts=Mounts(),  # type: ignore[arg-type]
        target_resolver=Targets(),
    )

    with pytest.raises(StudioToolExecutionError, match="尚未挂载"):
        await registry.execute(
            name="execute_in_sandbox",
            executor_revision="aio-shell-v2",
            arguments={"environment_id": "e" * 32, "command": "pwd"},
            context=_context(),
        )


@pytest.mark.asyncio
async def test_registered_tool_uses_only_the_current_context_mount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[SessionEnvironmentMount, str]] = []

    class Mounts:
        @staticmethod
        def get(
            context: StudioToolExecutionContext, environment_id: str = ""
        ) -> SessionEnvironmentMount:
            assert context.environment_mount is not None
            assert environment_id == "e" * 32
            return context.environment_mount

    class Targets:
        async def resolve(
            self,
            mount: SessionEnvironmentMount,
            context: StudioToolExecutionContext,
        ) -> SandboxExecutionTarget:
            seen.append((mount, context.session_id))
            return SandboxExecutionTarget(
                endpoint="https://sandbox.example?Authorization=secret",
                session_id="sandbox-1",
            )

    async def fake_execute(
        target: SandboxExecutionTarget,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        return {"ok": True, "session": target.session_id, **arguments}

    monkeypatch.setattr(
        "frontend.server.studio_tools.sandbox_shell.execute_in_sandbox",
        fake_execute,
    )
    registry = StudioToolRegistry()
    register_sandbox_shell_tool(
        registry,
        mounts=Mounts(),  # type: ignore[arg-type]
        target_resolver=Targets(),
    )

    result = await registry.execute(
        name="execute_in_sandbox",
        executor_revision="aio-shell-v2",
        arguments={"environment_id": "e" * 32, "command": "lark-cli --version"},
        context=_context("session-b", mount=_mount()),
    )

    assert result == {
        "ok": True,
        "session": "sandbox-1",
        "command": "lark-cli --version",
    }
    assert seen == [(_mount(), "session-b")]


@pytest.mark.asyncio
async def test_agentkit_resolver_reuses_tool_and_session_per_agent_session() -> None:
    client = _FakeAgentkitClient()
    mount = replace(_mount(), mount_instance_id="mount-1")
    _remember_tool(client, mount)
    resolver = AgentkitEnvironmentSandboxResolver(
        lambda provider, region: client,
        poll_interval_seconds=0,
    )

    first = await resolver.prepare(mount, _context(mount=mount))
    repeated = await resolver.resolve(mount, _context(mount=mount))
    second_session = await resolver.prepare(mount, _context("session-2", mount=mount))
    restarted_resolver = AgentkitEnvironmentSandboxResolver(
        lambda provider, region: client,
        poll_interval_seconds=0,
    )
    after_restart = await restarted_resolver.prepare(mount, _context(mount=mount))

    assert first == repeated
    assert after_restart.session_id == first.session_id
    assert first.session_id != second_session.session_id
    assert client.created_tools == []
    assert len(client.created_sessions) == 2


@pytest.mark.asyncio
async def test_agentkit_resolver_revalidates_cached_tool_and_session() -> None:
    client = _FakeAgentkitClient()
    mount = replace(_mount(), mount_instance_id="mount-1")
    context = _context(mount=mount)
    _remember_tool(client, mount)
    resolver = AgentkitEnvironmentSandboxResolver(
        lambda provider, region: client,
        poll_interval_seconds=0,
    )

    first = await resolver.prepare(mount, context)
    repeated = await resolver.prepare(mount, context)

    assert repeated is first
    assert client.got_tool_ids == [mount.tool_id, mount.tool_id]
    assert client.got_session_ids == [first.session_id]
    assert len(client.created_sessions) == 1


@pytest.mark.asyncio
async def test_agentkit_resolver_repairs_deleted_cached_session() -> None:
    client = _FakeAgentkitClient()
    mount = replace(_mount(), mount_instance_id="mount-1")
    context = _context(mount=mount)
    _remember_tool(client, mount)
    resolver = AgentkitEnvironmentSandboxResolver(
        lambda provider, region: client,
        poll_interval_seconds=0,
    )

    stale = await resolver.prepare(mount, context)
    client.sessions.clear()

    repaired = await resolver.prepare(mount, context)

    assert repaired.session_id != stale.session_id
    assert resolver.is_prepared(mount, context) is True
    assert await resolver.resolve(mount, context) is repaired
    assert client.got_session_ids == [stale.session_id]
    assert len(client.created_sessions) == 2


@pytest.mark.asyncio
async def test_agentkit_resolver_requires_mount_preparation_before_tool_call() -> None:
    client = _FakeAgentkitClient()
    mount = replace(_mount(), mount_instance_id="mount-1")
    _remember_tool(client, mount)
    resolver = AgentkitEnvironmentSandboxResolver(
        lambda provider, region: client,
        poll_interval_seconds=0,
    )

    with pytest.raises(SandboxResolutionError, match="was not prepared"):
        await resolver.resolve(mount, _context(mount=mount))

    assert client.created_tools == []
    assert client.created_sessions == []


@pytest.mark.asyncio
async def test_agentkit_resolver_does_not_reuse_across_environment_versions() -> None:
    client = _FakeAgentkitClient()
    first = _mount()
    replacement = replace(first, environment_version_id="version-2")
    _remember_tool(client, first)
    resolver = AgentkitEnvironmentSandboxResolver(
        lambda provider, region: client,
        poll_interval_seconds=0,
    )
    context = _context(mount=first)

    first_target = await resolver.prepare(first, context)
    replacement_target = await resolver.prepare(replacement, context)

    assert first_target.session_id != replacement_target.session_id
    assert len(client.created_sessions) == 2


@pytest.mark.asyncio
async def test_agentkit_resolver_does_not_reuse_across_images() -> None:
    client = _FakeAgentkitClient()
    first = _mount()
    replacement = replace(first, image="registry.example/anr-review:v2")
    _remember_tool(client, first)
    resolver = AgentkitEnvironmentSandboxResolver(
        lambda provider, region: client,
        poll_interval_seconds=0,
    )
    context = _context(mount=first)

    first_target = await resolver.prepare(first, context)
    client.tools[0].image_url = replacement.image
    replacement_target = await resolver.prepare(replacement, context)

    assert first_target.session_id != replacement_target.session_id
    assert len(client.created_sessions) == 2


@pytest.mark.asyncio
async def test_agentkit_resolver_does_not_reuse_after_remount() -> None:
    client = _FakeAgentkitClient()
    first = replace(_mount(), mount_instance_id="mount-1")
    remounted = replace(first, mount_instance_id="mount-2")
    _remember_tool(client, first)
    resolver = AgentkitEnvironmentSandboxResolver(
        lambda provider, region: client,
        poll_interval_seconds=0,
    )
    context = _context(mount=first)

    first_target = await resolver.prepare(first, context)
    remounted_target = await resolver.prepare(remounted, context)

    assert first_target.session_id != remounted_target.session_id
    assert len(client.created_sessions) == 2


@pytest.mark.asyncio
async def test_agentkit_resolver_reuses_legacy_mount_without_instance_id() -> None:
    client = _FakeAgentkitClient()
    mount = _mount()
    _remember_tool(client, mount)
    resolver = AgentkitEnvironmentSandboxResolver(
        lambda provider, region: client,
        poll_interval_seconds=0,
    )
    context = _context(mount=mount)

    first_target = await resolver.prepare(mount, context)
    repeated_target = await resolver.resolve(replace(mount), context)

    assert first_target is repeated_target
    assert len(client.created_sessions) == 1


@pytest.mark.asyncio
async def test_agentkit_resolver_uses_persisted_ready_tool_id() -> None:
    client = _FakeAgentkitClient()
    resolver = AgentkitEnvironmentSandboxResolver(
        lambda provider, region: client,
        poll_interval_seconds=0,
    )
    mount = replace(_mount(), tool_id="tool-persisted", tool_status="ready")
    _remember_tool(client, mount)

    target = await resolver.prepare(mount, _context(mount=mount))

    assert target.tool_id == "tool-persisted"
    assert client.created_tools == []
    assert len(client.created_sessions) == 1


@pytest.mark.asyncio
async def test_agentkit_resolver_waits_for_session_ready_even_with_endpoint() -> None:
    class TransitionalClient(_FakeAgentkitClient):
        polls = 0

        def get_session(self, request: Any) -> Any:
            session = super().get_session(request)
            self.polls += 1
            if self.polls == 1:
                return SimpleNamespace(**{**session.__dict__, "status": "Creating"})
            session.status = "Ready"
            return session

    client = TransitionalClient()
    mount = _mount()
    context = _context(mount=mount)
    _remember_tool(client, mount)
    client.sessions.append(
        SimpleNamespace(
            session_id="sandbox-existing",
            tool_id=mount.tool_id,
            user_session_id=_user_session_id(context, mount),
            endpoint="https://sandbox.example?Authorization=secret",
            status="Creating",
        )
    )
    resolver = AgentkitEnvironmentSandboxResolver(
        lambda provider, region: client,
        poll_interval_seconds=0,
    )

    target = await resolver.prepare(mount, context)

    assert target.session_id == "sandbox-existing"
    assert client.polls == 2


@pytest.mark.asyncio
async def test_agentkit_resolver_does_not_cache_across_persisted_tool_ids() -> None:
    client = _FakeAgentkitClient()
    first = _mount()
    replacement = replace(first, tool_id="tool-replacement")
    _remember_tool(client, first)
    _remember_tool(client, replacement)
    resolver = AgentkitEnvironmentSandboxResolver(
        lambda provider, region: client,
        poll_interval_seconds=0,
    )
    context = _context(mount=first)

    first_target = await resolver.prepare(first, context)
    replacement_target = await resolver.prepare(replacement, context)

    assert first_target.tool_id == "tool-persisted"
    assert replacement_target.tool_id == "tool-replacement"
    assert first_target.session_id != replacement_target.session_id
    assert len(client.created_sessions) == 2


@pytest.mark.asyncio
async def test_agentkit_resolver_rejects_persisted_tool_that_is_not_ready() -> None:
    client = _FakeAgentkitClient()
    mount = _mount()
    _remember_tool(client, mount, status="Creating")
    resolver = AgentkitEnvironmentSandboxResolver(
        lambda provider, region: client,
        poll_interval_seconds=0,
    )

    with pytest.raises(RuntimeError, match=r"not Ready \(status: creating\)"):
        await resolver.prepare(mount, _context(mount=mount))

    assert client.created_tools == []
    assert client.created_sessions == []


@pytest.mark.asyncio
async def test_registered_tool_surfaces_non_ready_persisted_tool() -> None:
    client = _FakeAgentkitClient()
    mount = _mount()
    _remember_tool(client, mount, status="Creating")

    class Mounts:
        @staticmethod
        def get(
            context: StudioToolExecutionContext, environment_id: str = ""
        ) -> SessionEnvironmentMount:
            del context, environment_id
            return mount

    resolver = AgentkitEnvironmentSandboxResolver(
        lambda provider, region: client,
        poll_interval_seconds=0,
    )
    registry = StudioToolRegistry()
    register_sandbox_shell_tool(
        registry,
        mounts=Mounts(),  # type: ignore[arg-type]
        target_resolver=resolver,
    )

    with pytest.raises(RuntimeError, match=r"not Ready \(status: creating\)"):
        await resolver.prepare(mount, _context(mount=mount))

    with pytest.raises(StudioToolExecutionError, match="was not prepared"):
        await registry.execute(
            name="execute_in_sandbox",
            executor_revision="aio-shell-v2",
            arguments={"environment_id": "e" * 32, "command": "pwd"},
            context=_context(mount=mount),
        )


@pytest.mark.asyncio
async def test_agentkit_resolver_rejects_unavailable_persisted_tool_id() -> None:
    client = _FakeAgentkitClient()
    mount = _mount()
    resolver = AgentkitEnvironmentSandboxResolver(
        lambda provider, region: client,
        poll_interval_seconds=0,
    )

    with pytest.raises(RuntimeError, match="persisted Sandbox Tool is unavailable"):
        await resolver.prepare(mount, _context(mount=mount))

    assert client.created_tools == []
    assert client.created_sessions == []


@pytest.mark.asyncio
async def test_agentkit_resolver_rejects_mount_without_persisted_tool_id() -> None:
    client = _FakeAgentkitClient()
    resolver = AgentkitEnvironmentSandboxResolver(
        lambda provider, region: client,
        poll_interval_seconds=0,
    )
    mount = replace(_mount(), tool_id="", tool_status="")

    with pytest.raises(RuntimeError, match="persisted Tool"):
        await resolver.prepare(mount, _context(mount=mount))

    assert client.created_tools == []
    assert client.created_sessions == []


@pytest.mark.asyncio
async def test_environment_tools_list_describe_and_enforce_mount_whitelist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _mount("registry.example/environment:first")
    second = SessionEnvironmentMount(
        environment_id="f" * 32,
        environment_version_id="version-2",
        image="registry.example/environment:second",
        provider="volcengine",
        region="cn-beijing",
        name="Python data",
        description="Data analysis tools",
        manifest={
            "apiVersion": "agentkit.studio/v1alpha1",
            "kind": "Environment",
            "metadata": {"id": "f" * 32, "name": "Python data"},
            "spec": {"capabilities": ["shell", "python"]},
        },
    )

    class Mounts:
        @staticmethod
        def get_all(
            context: StudioToolExecutionContext,
        ) -> tuple[SessionEnvironmentMount, ...]:
            return context.environment_mounts

        @staticmethod
        def get(
            context: StudioToolExecutionContext, environment_id: str = ""
        ) -> SessionEnvironmentMount:
            for mount in context.environment_mounts:
                if mount.environment_id == environment_id:
                    return mount
            raise ValueError("该环境未挂载到当前会话。")

    class Targets:
        async def resolve(
            self,
            mount: SessionEnvironmentMount,
            context: StudioToolExecutionContext,
        ) -> SandboxExecutionTarget:
            return SandboxExecutionTarget(
                endpoint="https://sandbox.example?Authorization=secret",
                session_id=f"sandbox-{mount.environment_id[0]}",
            )

    async def fake_execute(
        target: SandboxExecutionTarget,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        return {"sandbox_session_id": target.session_id, **arguments}

    monkeypatch.setattr(
        "frontend.server.studio_tools.sandbox_shell.execute_in_sandbox",
        fake_execute,
    )
    registry = StudioToolRegistry()
    register_sandbox_shell_tool(
        registry,
        mounts=Mounts(),  # type: ignore[arg-type]
        target_resolver=Targets(),
    )
    manifests = {item["name"]: item for item in registry.snapshot().manifests()}
    assert (
        "first tool for every substantive request"
        in (manifests["list_envs"]["description"])
    )
    assert "semantic match" in manifests["list_envs"]["description"]
    assert "select it exactly" in manifests["list_envs"]["description"]
    assert "Requirement/design/ADR" in manifests["list_envs"]["description"]
    assert "priority over creating" in manifests["list_envs"]["description"]
    assert "instead of creating" in manifests["execute_in_sandbox"]["description"]
    context = _context(mounts=(first, second))

    listed = await registry.execute(
        name="list_envs",
        executor_revision="environment-catalog-v1",
        arguments={},
        context=context,
    )
    manifest = await registry.execute(
        name="get_env_manifest",
        executor_revision="environment-catalog-v1",
        arguments={"environment_id": "f" * 32},
        context=context,
    )
    executed = await registry.execute(
        name="execute_in_sandbox",
        executor_revision="aio-shell-v2",
        arguments={"environment_id": "f" * 32, "command": "python --version"},
        context=context,
    )

    assert listed == {
        "environments": [
            {
                "environment_id": "e" * 32,
                "environment_version_id": "version-1",
                "name": "AIO environment",
                "description": "Includes common CLIs",
                "base_environment": "",
                "capabilities": ["shell", "cli"],
            },
            {
                "environment_id": "f" * 32,
                "environment_version_id": "version-2",
                "name": "Python data",
                "description": "Data analysis tools",
                "base_environment": "",
                "capabilities": ["shell", "python"],
            },
        ]
    }
    assert manifest == second.manifest
    assert executed == {
        "sandbox_session_id": "sandbox-f",
        "command": "python --version",
    }
    with pytest.raises(StudioToolExecutionError, match="未挂载"):
        await registry.execute(
            name="get_env_manifest",
            executor_revision="environment-catalog-v1",
            arguments={"environment_id": "a" * 32},
            context=context,
        )


@pytest.mark.asyncio
async def test_execute_tool_rejects_codex_environment_fallback() -> None:
    codex_mount = replace(
        _mount(),
        manifest={
            "apiVersion": "agentkit.studio/v1alpha1",
            "kind": "Environment",
            "metadata": {"id": "e" * 32, "name": "Codex environment"},
            "spec": {
                "baseEnvironment": "codex-sandbox",
                "capabilities": ["shell", "cli"],
            },
        },
    )

    class Mounts:
        @staticmethod
        def get(
            context: StudioToolExecutionContext, environment_id: str = ""
        ) -> SessionEnvironmentMount:
            del context, environment_id
            return codex_mount

        @staticmethod
        def get_all(
            context: StudioToolExecutionContext,
        ) -> tuple[SessionEnvironmentMount, ...]:
            del context
            return (codex_mount,)

    class Targets:
        async def resolve(
            self,
            mount: SessionEnvironmentMount,
            context: StudioToolExecutionContext,
        ) -> SandboxExecutionTarget:
            raise AssertionError((mount, context))

    registry = StudioToolRegistry()
    register_sandbox_shell_tool(
        registry,
        mounts=Mounts(),  # type: ignore[arg-type]
        target_resolver=Targets(),
    )

    with pytest.raises(
        StudioToolExecutionError,
        match="delegate_to_codex_sandbox",
    ):
        await registry.execute(
            name="execute_in_sandbox",
            executor_revision="aio-shell-v2",
            arguments={"environment_id": "e" * 32, "command": "pwd"},
            context=_context(mount=codex_mount),
        )


@pytest.mark.asyncio
async def test_agentkit_resolver_reuses_each_environment_session_independently() -> (
    None
):
    client = _FakeAgentkitClient()
    resolver = AgentkitEnvironmentSandboxResolver(
        lambda provider, region: client,
        poll_interval_seconds=0,
    )
    first = _mount("registry.example/environment:first")
    second = SessionEnvironmentMount(
        **{
            **first.__dict__,
            "environment_id": "f" * 32,
            "image": "registry.example/environment:second",
            "tool_id": "tool-second",
        }
    )
    _remember_tool(client, first)
    _remember_tool(client, second)
    context = _context(mounts=(first, second))

    assert resolver.is_prepared(first, context) is False
    assert resolver.is_prepared(second, context) is False
    first_target, second_target = await resolver.prepare_many((first, second), context)

    assert resolver.is_prepared(first, context) is True
    assert resolver.is_prepared(second, context) is True
    assert await resolver.resolve(first, context) is first_target
    assert await resolver.resolve(second, context) is second_target
    assert first_target.session_id != second_target.session_id
    assert len(client.created_sessions) == 2


def json_body(content: bytes) -> dict[str, Any]:
    import json

    value = json.loads(content)
    assert isinstance(value, dict)
    return value


def _remember_tool(
    client: _FakeAgentkitClient,
    mount: SessionEnvironmentMount,
    *,
    status: str = "Ready",
) -> None:
    client.tools.append(
        SimpleNamespace(
            tool_id=mount.tool_id,
            image_url=mount.image,
            status=status,
        )
    )


class _FakeAgentkitClient:
    def __init__(self) -> None:
        self.tools: list[Any] = []
        self.sessions: list[Any] = []
        self.created_tools: list[Any] = []
        self.created_sessions: list[Any] = []
        self.got_tool_ids: list[str] = []
        self.got_session_ids: list[str] = []

    def list_tools(self, request: Any) -> Any:
        name = request.filters[0].values[0]
        return SimpleNamespace(
            tools=[item for item in self.tools if item.name == name],
            next_token="",
        )

    def create_tool(self, request: Any) -> Any:
        self.created_tools.append(request)
        tool = SimpleNamespace(
            name=request.name,
            project_name=request.project_name,
            tool_type=request.tool_type,
            tool_id="tool-1",
            image_url=request.image_url,
            command=request.command,
            port=request.port,
            envs=request.envs,
            status="Ready",
        )
        self.tools.append(tool)
        return tool

    def update_tool(self, request: Any) -> Any:
        tool = next(item for item in self.tools if item.tool_id == request.tool_id)
        tool.image_url = request.image_url
        tool.command = request.command
        tool.port = request.port
        tool.envs = request.envs
        return tool

    def get_tool(self, request: Any) -> Any:
        self.got_tool_ids.append(request.tool_id)
        return next(item for item in self.tools if item.tool_id == request.tool_id)

    def list_sessions(self, request: Any) -> Any:
        user_session_id = request.filters[0].values[0]
        return SimpleNamespace(
            session_infos=[
                item
                for item in self.sessions
                if item.tool_id == request.tool_id
                and item.user_session_id == user_session_id
            ]
        )

    def create_session(self, request: Any) -> Any:
        self.created_sessions.append(request)
        sequence = len(self.created_sessions)
        session = SimpleNamespace(
            session_id=f"sandbox-{sequence}",
            tool_id=request.tool_id,
            user_session_id=request.user_session_id,
            endpoint=(f"https://sandbox-{sequence}.example?Authorization=secret"),
            status="Ready",
        )
        self.sessions.append(session)
        return session

    def get_session(self, request: Any) -> Any:
        self.got_session_ids.append(request.session_id)
        return next(
            item for item in self.sessions if item.session_id == request.session_id
        )
