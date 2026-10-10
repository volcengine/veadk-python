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

import asyncio
import importlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

try:
    from builtins import BaseExceptionGroup
except ImportError:  # Python 3.10
    from exceptiongroup import BaseExceptionGroup


agent_module = importlib.import_module("veadk.runtime.managed_agents.sandbox")
SandboxSessionManager = agent_module.SandboxSessionManager

main_module = importlib.import_module("veadk.runtime.managed_agents.worker")


def test_managed_memory_ignores_legacy_postgresql_configuration(monkeypatch):
    from google.adk.sessions import InMemorySessionService

    monkeypatch.setenv(
        "VEADK_MANAGED_SESSION_DB_URL", "postgresql://invalid.invalid/db"
    )
    memory = main_module.managed_short_term_memory()
    assert isinstance(memory.session_service, InMemorySessionService)


class _FakeClient:
    def __init__(self, remote_session_id: str):
        self.session_id = None
        self.remote_session_id = remote_session_id
        self.created_titles = []
        self.idle_count = 0

    def create_session(self, title: str):
        self.created_titles.append(title)
        self.session_id = self.remote_session_id

    def post_status_idle(self):
        self.idle_count += 1


def test_each_veadk_session_creates_a_distinct_remote_session(monkeypatch):
    manager = SandboxSessionManager()
    clients = iter((_FakeClient("remote-1"), _FakeClient("remote-2")))
    monkeypatch.setattr(manager, "_new_client", lambda: next(clients))

    assert manager.create_remote_session("veadk-1") == "remote-1"
    assert manager.create_remote_session("veadk-1") == "remote-1"
    assert manager.create_remote_session("veadk-2") == "remote-2"

    assert manager.get("veadk-1") is not manager.get("veadk-2")
    assert manager.get("veadk-1").created_titles == [
        "VeADK Self-Hosted Sandbox Session veadk-1"
    ]
    assert manager.get("veadk-2").created_titles == [
        "VeADK Self-Hosted Sandbox Session veadk-2"
    ]


def test_remote_session_writes_no_synthetic_event_and_idles_once_per_turn(
    monkeypatch,
):
    manager = SandboxSessionManager()
    client = _FakeClient("remote-1")
    monkeypatch.setattr(manager, "_new_client", lambda: client)
    manager.create_remote_session("veadk-1")

    manager.begin_turn("veadk-1")
    manager.begin_turn("veadk-1")

    manager.end_turn("veadk-1")
    assert client.idle_count == 0
    manager.end_turn("veadk-1")
    assert client.idle_count == 1

    manager.begin_turn("veadk-1")
    manager.begin_turn("veadk-1")
    manager.end_turn("veadk-1")
    manager.end_turn("veadk-1")
    assert client.idle_count == 2


def test_runner_wrapper_ends_remote_turn_after_failure(monkeypatch):
    lifecycle_calls = []

    class _FailingRunner:
        async def run_async(self, **kwargs):
            yield "started"
            raise RuntimeError("turn failed")

    monkeypatch.setattr(
        agent_module.sandbox_sessions,
        "begin_turn",
        lambda session_id: lifecycle_calls.append(("begin", session_id)),
    )
    monkeypatch.setattr(
        agent_module.sandbox_sessions,
        "end_turn",
        lambda session_id: lifecycle_calls.append(("end", session_id)),
    )
    runner = agent_module.enable_sandbox_turn_lifecycle(_FailingRunner())

    async def consume():
        async for _ in runner.run_async(session_id="veadk-1"):
            pass

    try:
        asyncio.run(consume())
    except RuntimeError as error:
        assert str(error) == "turn failed"
    else:
        raise AssertionError("the wrapped runner must preserve turn failures")

    assert lifecycle_calls == [("begin", "veadk-1"), ("end", "veadk-1")]


def test_dispatch_task_sends_only_the_model_tool_call(monkeypatch):
    dispatched = []
    client = SimpleNamespace(
        dispatch_tool=lambda name, arguments, *, dispatch_id: (
            dispatched.append((name, arguments, dispatch_id)) or {"stdout": "ok"}
        )
    )
    monkeypatch.setattr(agent_module.sandbox_sessions, "get", lambda session_id: client)
    tool_call = SimpleNamespace(
        session_id="veadk-session",
        id="tool-call-1",
        name="bash",
        arguments={"command": "printf ok"},
    )

    result = asyncio.run(agent_module.dispatch_task(tool_call))

    assert result == {"stdout": "ok"}
    assert dispatched == [("bash", {"command": "printf ok"}, "tool-call-1")]
    assert not hasattr(agent_module.get_default_agent(), "run_turn")


def test_managed_agent_config_uses_frozen_snapshot():
    config = main_module.managed_agent_config(
        {
            "name": "Distributed Agent",
            "description": "test",
            "model": {"id": "model-from-session"},
            "system": "Remember prior turns.",
            "tools": [],
        }
    )

    assert config["name"] == "Distributed_Agent"
    assert config["model_name"] == "model-from-session"
    assert config["instruction"] == "Remember prior turns."
    assert config["tools"] == []
    assert config["before_tool_callback"] is None


def test_nested_http_status_detection_handles_task_group_authentication():
    authentication = RuntimeError("redacted")
    authentication.status_code = 401
    nested = BaseExceptionGroup("dispatcher", [authentication])

    assert main_module._contains_http_status(nested, {401, 403})
    assert not main_module._contains_http_status(nested, {429, 503})


def test_dispatcher_refreshes_identity_after_startup_401(monkeypatch):
    runs = 0
    invalidations = 0
    sleeps = []

    class Dispatcher:
        async def run(self, **kwargs):
            nonlocal runs
            runs += 1
            assert kwargs == {"max_items": 1, "max_concurrency": 2}
            if runs == 1:
                error = RuntimeError("redacted")
                error.status_code = 401
                raise BaseExceptionGroup("poll", [error])
            return 7

    class Provider:
        def invalidate(self):
            nonlocal invalidations
            invalidations += 1

    async def no_wait(delay):
        sleeps.append(delay)

    monkeypatch.setattr(main_module.asyncio, "sleep", no_wait)
    result = asyncio.run(
        main_module._run_dispatcher_with_identity_retry(
            Dispatcher, Provider(), max_items=1, max_concurrency=2
        )
    )

    assert result == 7
    assert runs == 2
    assert invalidations == 1
    assert sleeps == [1.0]


def test_dispatcher_does_not_restart_after_shutdown_during_auth_backoff(monkeypatch):
    runs = 0
    stopping = False

    class Dispatcher:
        async def run(self, **kwargs):
            nonlocal runs
            runs += 1
            error = RuntimeError("redacted")
            error.status_code = 401
            raise error

    class Provider:
        def invalidate(self):
            pass

    async def request_stop(_delay):
        nonlocal stopping
        stopping = True

    monkeypatch.setattr(main_module.asyncio, "sleep", request_stop)
    result = asyncio.run(
        main_module._run_dispatcher_with_identity_retry(
            Dispatcher,
            Provider(),
            max_items=None,
            max_concurrency=1,
            should_stop=lambda: stopping,
        )
    )

    assert result == 0
    assert runs == 1


def test_dispatcher_drains_new_instance_when_shutdown_races_with_factory():
    stopping = False
    runs = 0
    drains = 0

    class Dispatcher:
        async def run(self, **kwargs):
            nonlocal runs
            runs += 1
            return 1

        def drain(self):
            nonlocal drains
            drains += 1

    def factory():
        nonlocal stopping
        dispatcher = Dispatcher()
        stopping = True
        return dispatcher

    result = asyncio.run(
        main_module._run_dispatcher_with_identity_retry(
            factory,
            None,
            max_items=None,
            max_concurrency=1,
            should_stop=lambda: stopping,
        )
    )

    assert result == 0
    assert drains == 1
    assert runs == 0


def test_identity_retry_can_wrap_readiness_poll(monkeypatch):
    polls = 0
    invalidations = 0

    async def poll():
        nonlocal polls
        polls += 1
        if polls == 1:
            error = RuntimeError("redacted")
            error.status_code = 403
            raise error

    class Provider:
        def invalidate(self):
            nonlocal invalidations
            invalidations += 1

    async def no_wait(_delay):
        pass

    monkeypatch.setattr(main_module.asyncio, "sleep", no_wait)
    assert asyncio.run(main_module._run_with_identity_retry(poll, Provider())) is None
    assert polls == 2
    assert invalidations == 1


def test_managed_agent_config_rejects_unknown_enabled_tool():
    snapshot = {
        "name": "demo",
        "model": "model",
        "tools": [
            {
                "type": "agent_toolset_20260401",
                "configs": [{"name": "unknown", "enabled": True}],
            }
        ],
    }

    try:
        main_module.managed_agent_config(snapshot)
    except ValueError as error:
        assert "unknown" in str(error)
    else:
        raise AssertionError("unknown enabled tools must be rejected")


def test_managed_agent_config_applies_toolset_defaults_and_overrides():
    snapshot = {
        "name": "demo",
        "model": "model",
        "tools": [
            {
                "type": "agent_toolset_20260401",
                "default_config": {"enabled": False},
                "configs": [
                    {"name": "bash", "enabled": True},
                    {"name": "read", "enabled": True},
                ],
            }
        ],
    }

    config = main_module.managed_agent_config(snapshot)

    assert [tool.__name__ for tool in config["tools"]] == ["bash", "read"]


def test_managed_agent_config_requires_runtime_context_for_custom_tools():
    custom_snapshot = {
        "name": "demo",
        "model": "model",
        "tools": [{"type": "custom", "name": "external_tool"}],
    }
    try:
        main_module.managed_agent_config(custom_snapshot)
    except ValueError as error:
        assert "custom" in str(error)
    else:
        raise AssertionError("unsupported top-level tool definitions must be rejected")


def test_managed_agent_config_ignores_skills_without_metadata():
    snapshot = {
        "name": "demo",
        "model": "model",
        "tools": [],
        "skills": [{"type": "custom", "skill_id": "skill_x", "version": "v1"}],
    }
    config = main_module.managed_agent_config(snapshot)
    assert "managed_agent_skills" not in config["instruction"]


def test_managed_agent_config_loads_materialized_skill_instructions(tmp_path):
    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "# demo-skill\n\nDemo instructions.", encoding="utf-8"
    )
    snapshot = {
        "name": "demo",
        "model": "model",
        "skills": [{"type": "custom", "skill_id": "skill_x", "version": "v1"}],
        "tools": [
            {
                "type": "custom",
                "name": "approve",
                "description": "Approve",
                "input_schema": {"type": "object"},
            }
        ],
    }
    config = main_module.managed_agent_config(
        snapshot,
        sdk=SimpleNamespace(),
        session_id="session-1",
        skill_dirs=[skill_dir],
    )
    assert "name='demo-skill'" in config["instruction"]
    assert "# demo-skill\n\nDemo instructions." in config["instruction"]
    assert str(skill_dir / "SKILL.md") in config["instruction"]
    assert [tool.name for tool in config["tools"]] == ["approve"]


@pytest.mark.parametrize("result_type", ["user.tool_result", "agent.tool_result"])
def test_managed_worker_remote_tool_waits_for_matching_result(monkeypatch, result_type):
    monkeypatch.setenv("MANAGED_AGENT_TOOL_EXECUTION", "remote")
    batches = []

    async def send(session_id, *, events):
        batches.extend(events)

    async def list_events(session_id, **kwargs):
        yield {"type": "user.tool_result", "tool_use_id": "other", "content": "wrong"}
        yield {
            "type": result_type,
            "tool_use_id": "tool-1",
            "content": "remote-ok",
            "is_error": False,
        }

    async def forbidden_local(*args, **kwargs):
        raise AssertionError("remote tools must not execute inside Agent Loop")

    monkeypatch.setattr(main_module, "_run_managed_tool", forbidden_local)
    sdk = SimpleNamespace(
        beta=SimpleNamespace(
            sessions=SimpleNamespace(
                events=SimpleNamespace(send=send, list=list_events)
            )
        )
    )
    runtime = main_module.managed_work_tool_runtime(
        sdk, "session-1", workdir=Path("/tmp/managed-work")
    )
    result = asyncio.run(
        runtime.execute(
            SimpleNamespace(
                id="tool-1",
                name="bash",
                arguments={"command": "printf remote-ok"},
                tool=SimpleNamespace(),
            )
        )
    )
    assert result == {"result": "remote-ok"}
    expected = ["agent.tool_use"]
    if result_type == "user.tool_result":
        expected.append("agent.tool_result")
        assert batches[-1]["tool_use_id"] == "tool-1"
        assert batches[-1]["content"] == "remote-ok"
    assert [event["type"] for event in batches] == expected


def test_managed_worker_executes_tool_locally_and_publishes_events(monkeypatch):
    sdk = SimpleNamespace(
        beta=SimpleNamespace(
            sessions=SimpleNamespace(events=SimpleNamespace(batches=[]))
        )
    )

    async def send(session_id, *, events):
        sdk.beta.sessions.events.batches.append((session_id, events))

    async def run_tool(name, arguments, *, workdir, native_tools=None):
        assert name == "bash"
        assert arguments == {"command": "printf ok"}
        assert workdir == Path("/tmp/managed-work")
        return {
            "status": "completed",
            "exit_code": 0,
            "stdout": "ok",
            "stderr": "",
        }

    sdk.beta.sessions.events.send = send
    monkeypatch.setattr(main_module, "_run_managed_tool", run_tool)
    runtime = main_module.managed_work_tool_runtime(
        sdk, "session-1", workdir=Path("/tmp/managed-work")
    )
    result = asyncio.run(
        runtime.execute(
            SimpleNamespace(
                id="tool-1",
                name="bash",
                arguments={"command": "printf ok"},
                tool=SimpleNamespace(),
            )
        )
    )

    assert result["stdout"] == "ok"
    emitted = [
        event for _, batch in sdk.beta.sessions.events.batches for event in batch
    ]
    assert emitted == [
        {
            "type": "agent.tool_use",
            "id": "tool-1",
            "name": "bash",
            "input": {"command": "printf ok"},
            "evaluated_permission": "allow",
        },
        {
            "type": "agent.tool_result",
            "tool_use_id": "tool-1",
            "content": "exit=0\nok",
            "is_error": False,
        },
    ]


def test_always_ask_tool_waits_for_confirmation(monkeypatch, tmp_path):
    sdk = SimpleNamespace(
        beta=SimpleNamespace(
            sessions=SimpleNamespace(events=SimpleNamespace(batches=[]))
        )
    )

    async def send(session_id, *, events):
        sdk.beta.sessions.events.batches.append((session_id, list(events)))

    class Page:
        def __aiter__(self):
            async def iterate():
                yield SimpleNamespace(
                    type="user.tool_confirmation",
                    tool_use_id="tool-ask",
                    result="allow",
                )

            return iterate()

    sdk.beta.sessions.events.send = send
    sdk.beta.sessions.events.list = lambda *args, **kwargs: Page()

    async def run_tool(*args, **kwargs):
        return {"status": "completed", "exit_code": 0, "stdout": "ok", "stderr": ""}

    monkeypatch.setattr(main_module, "_run_managed_tool", run_tool)
    runtime = main_module.managed_work_tool_runtime(
        sdk,
        "session-1",
        workdir=tmp_path,
        snapshot={
            "tools": [
                {
                    "type": "agent_toolset_20260401",
                    "default_config": {"enabled": False},
                    "configs": [
                        {
                            "name": "bash",
                            "enabled": True,
                            "permission_policy": {"type": "always_ask"},
                        }
                    ],
                }
            ]
        },
    )
    result = asyncio.run(
        runtime.execute(
            SimpleNamespace(
                id="tool-ask",
                name="bash",
                arguments={"command": "printf ok"},
                tool=SimpleNamespace(),
            )
        )
    )
    assert result["stdout"] == "ok"
    batches = [batch for _, batch in sdk.beta.sessions.events.batches]
    assert batches[0][0]["evaluated_permission"] == "ask"
    assert batches[0][1]["stop_reason"]["type"] == "requires_action"
    assert batches[1] == [{"type": "session.status_running"}]


def test_mcp_tool_executes_locally_and_publishes_mcp_events(tmp_path):
    sdk = SimpleNamespace(
        beta=SimpleNamespace(
            sessions=SimpleNamespace(events=SimpleNamespace(batches=[]))
        )
    )

    async def send(session_id, *, events):
        sdk.beta.sessions.events.batches.append((session_id, list(events)))

    class FakeMcpTool:
        name = "mcp__orders__lookup"
        _mcp_tool = object()
        managed_agents_mcp_server_name = "orders"

        async def run_async(self, *, args, tool_context):
            return {"order": args["id"]}

    sdk.beta.sessions.events.send = send
    runtime = main_module.managed_work_tool_runtime(
        sdk, "session-1", workdir=tmp_path, snapshot={"tools": []}
    )
    result = asyncio.run(
        runtime.execute(
            SimpleNamespace(
                id="mcp-call-1",
                name=FakeMcpTool.name,
                arguments={"id": "42"},
                tool=FakeMcpTool(),
                context=SimpleNamespace(),
            )
        )
    )
    assert result == {"order": "42"}
    emitted = [
        event for _, batch in sdk.beta.sessions.events.batches for event in batch
    ]
    assert emitted[0] == {
        "type": "agent.mcp_tool_use",
        "id": "mcp-call-1",
        "mcp_server_name": "orders",
        "name": "lookup",
        "input": {"id": "42"},
        "evaluated_permission": "allow",
    }
    assert emitted[1]["type"] == "agent.mcp_tool_result"
    assert emitted[1]["mcp_tool_use_id"] == "mcp-call-1"
    assert '"order": "42"' in emitted[1]["content"][0]["text"]


def test_managed_tool_environment_removes_control_plane_secrets(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_ENVIRONMENT_KEY", "secret")
    monkeypatch.setenv("DATABASE_POSTGRESQL_PASSWORD", "secret")
    monkeypatch.setenv("VEADK_MANAGED_SESSION_DB_URL", "secret")
    monkeypatch.setenv("MODEL_API_KEY", "secret")
    monkeypatch.setenv("SAFE_VALUE", "visible")

    environment = main_module._managed_tool_environment()

    assert "SAFE_VALUE" not in environment
    assert "ANTHROPIC_ENVIRONMENT_KEY" not in environment
    assert "DATABASE_POSTGRESQL_PASSWORD" not in environment
    assert "VEADK_MANAGED_SESSION_DB_URL" not in environment
    assert "MODEL_API_KEY" not in environment


def test_managed_worker_executes_real_local_tool(tmp_path):
    result = asyncio.run(
        main_module._run_managed_tool(
            "bash", {"command": "printf local-tool-ok"}, workdir=tmp_path
        )
    )

    assert result == {
        "status": "completed",
        "exit_code": 0,
        "stdout": "local-tool-ok",
        "stderr": "",
        "content": "local-tool-ok",
        "is_error": False,
    }


def test_managed_worker_times_out_local_tool(tmp_path):
    result = asyncio.run(
        main_module._run_managed_tool(
            "bash",
            {"command": "sleep 30", "timeout_ms": 20},
            workdir=tmp_path,
        )
    )

    assert result["status"] == "failed"
    assert result["is_error"] is True
    assert "timed out" in result["stderr"].lower()


def test_managed_tool_timeout_defaults_to_five_minutes(monkeypatch):
    monkeypatch.delenv(main_module.MANAGED_TOOL_TIMEOUT_ENV, raising=False)

    assert main_module._managed_tool_timeout_seconds() == 300.0


def test_managed_tool_timeout_honours_env_and_model_override(monkeypatch):
    monkeypatch.setenv(main_module.MANAGED_TOOL_TIMEOUT_ENV, "420")

    assert main_module._managed_tool_timeout_seconds() == 420.0


def test_action_timeout_never_truncates_the_tool_budget(monkeypatch):
    monkeypatch.delenv(main_module.MANAGED_TOOL_TIMEOUT_ENV, raising=False)
    monkeypatch.setenv("MANAGED_AGENT_ACTION_TIMEOUT_SECONDS", "180")

    assert main_module._managed_action_timeout_seconds() == 360.0

    monkeypatch.setenv("MANAGED_AGENT_ACTION_TIMEOUT_SECONDS", "900")
    assert main_module._managed_action_timeout_seconds() == 900.0

    monkeypatch.setenv(main_module.MANAGED_TOOL_TIMEOUT_ENV, "420")
    assert main_module._managed_action_timeout_seconds() == 900.0
    monkeypatch.setenv("MANAGED_AGENT_ACTION_TIMEOUT_SECONDS", "300")
    assert main_module._managed_action_timeout_seconds() == 480.0


def test_published_tool_use_carries_the_deployment_budget(monkeypatch):
    monkeypatch.delenv(main_module.MANAGED_TOOL_TIMEOUT_ENV, raising=False)

    annotated = main_module._with_default_tool_timeout(
        {"type": "agent.tool_use", "name": "bash", "input": {"command": "sleep 200"}}
    )
    assert annotated["input"]["timeout_ms"] == 300000
    assert annotated["input"]["command"] == "sleep 200"

    explicit = main_module._with_default_tool_timeout(
        {
            "type": "agent.tool_use",
            "name": "bash",
            "input": {"command": "ls", "timeout_ms": 1500},
        }
    )
    assert explicit["input"]["timeout_ms"] == 1500

    read_only = main_module._with_default_tool_timeout(
        {"type": "agent.tool_use", "name": "read", "input": {"file_path": "/tmp/x"}}
    )
    assert "timeout_ms" not in read_only["input"]

    monkeypatch.setenv(main_module.MANAGED_TOOL_TIMEOUT_ENV, "420")
    tuned = main_module._with_default_tool_timeout(
        {"type": "agent.tool_use", "name": "bash", "input": {"command": "true"}}
    )
    assert tuned["input"]["timeout_ms"] == 420000


def test_native_file_tools_preserve_content_and_do_not_spawn_shell(
    monkeypatch, tmp_path
):
    async def forbidden(*args, **kwargs):
        raise AssertionError("file tools must not invoke a subprocess")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden)

    async def run():
        tools = main_module.NativeAgentTools(tmp_path)
        content = "one\n' \" $HOME `uname` $(touch nope) &amp; 中文\nthree\n"
        try:
            written = await tools.run(
                "write", {"file_path": "nested/notes.txt", "content": content}
            )
            assert not written["is_error"]
            edited = await tools.run(
                "edit",
                {
                    "file_path": "nested/notes.txt",
                    "old_string": "three",
                    "new_string": "THREE",
                },
            )
            assert not edited["is_error"]
            read = await tools.run(
                "read", {"file_path": "nested/notes.txt", "view_range": [2, 3]}
            )
            assert "中文" in read["content"] and "THREE" in read["content"]
            assert (tmp_path / "nested/notes.txt").read_text() == content.replace(
                "three", "THREE"
            )
            assert (
                "notes.txt"
                in (await tools.run("glob", {"pattern": "**/*.txt"}))["content"]
            )
            assert "THREE" in (await tools.run("grep", {"pattern": "THREE"}))["content"]
            assert not (tmp_path / "nope").exists()
        finally:
            await tools.close()

    asyncio.run(run())


def test_native_file_tools_reject_symlink_escape_and_ambiguous_edit(tmp_path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("private")
    (tmp_path / "escape").symlink_to(outside)

    async def run():
        tools = main_module.NativeAgentTools(tmp_path)
        try:
            for name, arguments in [
                ("read", {"file_path": "escape"}),
                ("write", {"file_path": "escape", "content": "changed"}),
                ("glob", {"pattern": "../*"}),
                ("grep", {"pattern": "private", "path": ".."}),
            ]:
                assert (await tools.run(name, arguments))["is_error"]
            await tools.run("write", {"file_path": "repeat.txt", "content": "x x"})
            assert (
                await tools.run(
                    "edit",
                    {"file_path": "repeat.txt", "old_string": "x", "new_string": "y"},
                )
            )["is_error"]
            assert (tmp_path / "repeat.txt").read_text() == "x x"
            assert outside.read_text() == "private"
        finally:
            await tools.close()

    asyncio.run(run())


def test_native_bash_persists_state_and_restart_resets_it(tmp_path):
    async def run():
        tools = main_module.NativeAgentTools(tmp_path)
        try:
            await tools.run("bash", {"command": "export NATIVE_TEST_VALUE=kept"})
            assert (
                "kept"
                in (
                    await tools.run(
                        "bash", {"command": "printf '%s' \"$NATIVE_TEST_VALUE\""}
                    )
                )["content"]
            )
            assert not (await tools.run("bash", {"restart": True}))["is_error"]
            assert (
                "cleared"
                in (
                    await tools.run(
                        "bash",
                        {"command": "printf '%s' \"${NATIVE_TEST_VALUE-cleared}\""},
                    )
                )["content"]
            )
        finally:
            await tools.close()

    asyncio.run(run())


def test_feishu_channel_stays_up_until_stopped_and_shuts_down(monkeypatch):
    calls = []

    class _FakeRunner:
        def __init__(self, **kwargs):
            calls.append(("runner", kwargs))

        async def run_async(self, **kwargs):
            if False:
                yield None

    class _FakeChannel:
        def __init__(self, *, runner, **kwargs):
            calls.append(("channel", runner, kwargs))

        def start(self, loop):
            calls.append(("start", loop))

        async def shutdown(self):
            calls.append(("shutdown", None))

    monkeypatch.setattr(main_module, "Runner", _FakeRunner)
    monkeypatch.setattr(main_module, "FeishuChannelExtension", _FakeChannel)
    stop_event = asyncio.Event()
    stop_event.set()

    asyncio.run(main_module.serve_feishu_channel(stop_event))

    assert calls[0] == (
        "runner",
        {
            "agent": main_module.get_default_agent(),
            "app_name": "self_host_sandbox_demo",
        },
    )
    assert calls[1][0] == "channel"
    assert isinstance(calls[1][1], _FakeRunner)
    assert calls[1][2] == {
        "streaming": True,
        "show_thinking": True,
        "show_tool_calls": True,
        "show_tool_results": True,
        "separate_tool_call_cards": True,
        "separate_thinking_card": True,
        "create_topic": True,
    }
    assert calls[2][0] == "start"
    assert calls[3] == ("shutdown", None)


def test_managed_agent_model_base_url_is_taken_from_snapshot():
    config = main_module.managed_agent_config(
        {
            "name": "custom",
            "model": {"id": "model-x", "base_url": "https://model.example/api/v3"},
            "tools": [],
        }
    )
    assert config["model_name"] == "model-x"
    assert config["model_api_base"] == "https://model.example/api/v3"
    assert "model_api_key" not in config


def test_mcp_result_preserves_error_and_converts_image():
    content, error = main_module.mcp_result_content(
        {
            "isError": True,
            "content": [
                {"type": "text", "text": "failed"},
                {"type": "image", "data": "fixture", "mimeType": "image/png"},
            ],
        }
    )
    assert error is True
    assert content == [
        {"type": "text", "text": "failed"},
        {
            "type": "image",
            "source": {"type": "base64", "data": "fixture", "media_type": "image/png"},
        },
    ]
    assert main_module.mcp_result_content({"structuredContent": {"value": 42}}) == (
        [{"type": "text", "text": '{"value": 42}'}],
        False,
    )


@pytest.mark.parametrize("verdict", ["allow", "deny"])
def test_mcp_permission_gate_and_error_result(monkeypatch, tmp_path, verdict):
    monkeypatch.setenv("MANAGED_AGENT_TOOL_EXECUTION", "remote")
    emitted, calls = [], []

    async def send(session_id, *, events):
        emitted.extend(events)

    async def confirmed(*args, **kwargs):
        assert emitted[0]["evaluated_permission"] == "ask"
        assert calls == []
        return {"result": verdict}

    class Tool:
        name = "mcp__orders__lookup"
        _mcp_tool = object()
        managed_agents_mcp_server_name = "orders"

        async def run_async(self, *, args, tool_context):
            calls.append(args)
            return {"isError": True, "content": [{"type": "text", "text": "not found"}]}

    sdk = SimpleNamespace(
        beta=SimpleNamespace(
            sessions=SimpleNamespace(events=SimpleNamespace(send=send))
        )
    )
    monkeypatch.setattr(main_module, "_wait_for_session_event", confirmed)
    snapshot = {
        "tools": [
            {
                "type": "mcp_toolset",
                "mcp_server_name": "orders",
                "default_config": {"permission_policy": {"type": "always_ask"}},
            }
        ]
    }

    async def execute():
        runtime = main_module.managed_work_tool_runtime(
            sdk, "session", workdir=tmp_path, snapshot=snapshot
        )
        try:
            return await runtime.execute(
                SimpleNamespace(
                    id="call",
                    name=Tool.name,
                    arguments={"id": "42"},
                    tool=Tool(),
                    context=SimpleNamespace(),
                )
            )
        finally:
            await runtime.close()

    asyncio.run(execute())
    assert len(calls) == (1 if verdict == "allow" else 0)
    assert sum(e["type"] == "agent.mcp_tool_use" for e in emitted) == 1
    result = emitted[-1]
    assert result["type"] == "agent.mcp_tool_result"
    assert result["mcp_tool_use_id"] == "call" and result["is_error"] is True
    assert result["content"][0]["text"] == (
        "not found" if verdict == "allow" else "MCP tool call denied by user"
    )


def test_runner_cleanup_closes_all_toolsets_before_reporting_failure():
    closed = []

    class Toolset:
        def __init__(self, name, fail=False):
            self.name, self.fail = name, fail

        async def close(self):
            closed.append(self.name)
            if self.fail:
                raise RuntimeError("close failed")

    runner = SimpleNamespace(
        agent=SimpleNamespace(tools=[Toolset("first", True), Toolset("second")])
    )
    with pytest.raises(RuntimeError, match="close failed"):
        asyncio.run(main_module.close_managed_runner(runner))
    assert closed == ["first", "second"]


def test_native_cleanup_closes_context_after_tool_failure(monkeypatch):
    closed = []
    tools = object.__new__(main_module.NativeAgentTools)
    tools.tools = {"first": "first", "second": "second"}

    async def close_tool(tool):
        closed.append(tool)
        if tool == "first":
            raise RuntimeError("close failed")

    class Context:
        async def close(self):
            closed.append("context")

    tools.context = Context()
    monkeypatch.setattr(main_module, "aclose_runnable_tool", close_tool)
    with pytest.raises(RuntimeError, match="close failed"):
        asyncio.run(tools.close())
    assert closed == ["first", "second", "context"]


@pytest.mark.asyncio
async def test_native_tool_cleanup_sanitizes_both_failures_and_exits_context(caplog):
    from types import SimpleNamespace
    from veadk.runtime.managed_agents.worker import aclose_runnable_tool

    phases = []

    def close():
        phases.append("close")
        raise RuntimeError("private-cleanup-marker")

    class Context:
        async def __aexit__(self, *args):
            phases.append("exit")
            raise ValueError("private-exit-marker")

    await aclose_runnable_tool(SimpleNamespace(close=close, _context_manager=Context()))
    assert phases == ["close", "exit"]
    assert "private-cleanup-marker" not in caplog.text
    assert "private-exit-marker" not in caplog.text
    assert "RuntimeError" in caplog.text and "ValueError" in caplog.text


@pytest.mark.asyncio
async def test_native_tool_cleanup_awaits_close_and_preserves_cancellation():
    from types import SimpleNamespace
    from veadk.runtime.managed_agents.worker import aclose_runnable_tool

    phases = []

    async def close():
        phases.append("close")

    class Context:
        def __exit__(self, *args):
            phases.append("exit")

    await aclose_runnable_tool(SimpleNamespace(close=close, _context_manager=Context()))
    assert phases == ["close", "exit"]

    async def cancel():
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await aclose_runnable_tool(SimpleNamespace(aclose=cancel))
