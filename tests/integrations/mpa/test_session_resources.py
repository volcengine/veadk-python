from __future__ import annotations

import asyncio
import importlib
import io
import json
import logging
import socket
import subprocess
import sys
import textwrap
import time
import zipfile
from pathlib import Path
from types import ModuleType, SimpleNamespace

import anthropic
import httpx2
import pytest


resources = importlib.import_module("veadk.integrations.mpa.session_resources")
main = importlib.import_module("veadk.runtime.managed_agents.worker")


def test_managed_worker_short_term_memory_is_local_without_database_env(
    monkeypatch,
) -> None:
    for name in (
        "VEADK_MANAGED_SESSION_DB_URL",
        "DATABASE_POSTGRESQL_HOST",
        "DATABASE_POSTGRESQL_USER",
        "DATABASE_POSTGRESQL_PASSWORD",
        "DATABASE_POSTGRESQL_DATABASE",
    ):
        monkeypatch.delenv(name, raising=False)

    memory = main.managed_short_term_memory()

    assert memory.backend == "local"
    assert memory.db_url == ""
    assert type(memory.session_service).__name__ == "InMemorySessionService"


def test_managed_worker_entry_reaches_dispatcher_without_database_env(
    monkeypatch, tmp_path
) -> None:
    for name in (
        "VEADK_MANAGED_SESSION_DB_URL",
        "DATABASE_POSTGRESQL_HOST",
        "DATABASE_POSTGRESQL_USER",
        "DATABASE_POSTGRESQL_PASSWORD",
        "DATABASE_POSTGRESQL_DATABASE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MANAGED_AGENT_READY_FILE", str(tmp_path / "ready"))
    entered_poll = False

    class ClientContext:
        environment_id = "env-test"
        bearer_token = "synthetic-token"
        runtime_type = "default"
        _default_headers = {"X-Runtime-Type": "default"}

        def create_async_client(self):
            sdk = SimpleNamespace(base_url="http://controlled.invalid")

            class Context:
                async def __aenter__(self):
                    return sdk

                async def __aexit__(self, *_args):
                    return None

            return Context()

    class Dispatcher:
        def __init__(self, _sdk, **kwargs):
            assert kwargs["account_work"] is False
            assert kwargs["environment_id"] == "env-test"

        async def run(self, **_kwargs):
            nonlocal entered_poll
            entered_poll = True
            return 0

        def drain(self):
            return None

    monkeypatch.setattr(main, "SelfHostSandboxClient", ClientContext)
    dispatcher_module = ModuleType("anthropic.lib.environments._dispatcher")
    dispatcher_module.EnvironmentWorkDispatcher = Dispatcher
    monkeypatch.setitem(
        sys.modules, "veadk.runtime.managed_agents.dispatcher", dispatcher_module
    )

    result = asyncio.run(main.serve_managed_agent_worker(max_work_items=1))

    assert result == 0
    assert entered_poll is True
    assert not (tmp_path / "ready").exists()


def test_managed_agent_config_uses_durable_responses_contract() -> None:
    config = main.managed_agent_config(
        {
            "name": "managed",
            "model": "test-model",
            "tools": [],
            "skills": [],
        }
    )

    assert config["enable_responses"] is True
    assert config["enable_responses_cache"] is True
    assert config["model_extra_config"] == {
        "store": True,
        "retry_expired_response": False,
        "extra_body": {"caching": {"type": "disabled"}},
    }
    assert config["tools"] == []


def test_managed_agent_config_does_not_add_disabled_tools() -> None:
    config = main.managed_agent_config(
        {
            "name": "managed",
            "model": "test-model",
            "skills": [],
            "tools": [
                {
                    "type": "agent_toolset_20260401",
                    "default_config": {
                        "enabled": False,
                        "permission_policy": {"type": "always_allow"},
                    },
                    "configs": [
                        {
                            "type": "bash",
                            "name": "bash",
                            "enabled": False,
                        }
                    ],
                }
            ],
        }
    )

    assert config["tools"] == []
    assert config["before_tool_callback"] is None


def test_managed_agent_poll_trace_disabled_by_default(monkeypatch, caplog) -> None:
    monkeypatch.delenv("MANAGED_AGENT_POLL_TRACE", raising=False)
    with caplog.at_level(logging.INFO):
        main.configure_managed_agent_poll_trace(
            worker_id="worker-a",
            base_url="https://user:password@example.test/private?secret_key=value",
        )
    assert not [
        record
        for record in caplog.records
        if record.name == "anthropic.managed_agent_poll"
    ]


def test_managed_agent_poll_trace_ready_is_safe(monkeypatch, caplog) -> None:
    monkeypatch.setenv("MANAGED_AGENT_POLL_TRACE", "true")
    logger = logging.getLogger("anthropic.managed_agent_poll")
    logger.addHandler(caplog.handler)
    try:
        main.configure_managed_agent_poll_trace(
            worker_id="worker-a",
            base_url="https://user:password@example.test/private?secret_key=synthetic-secret",
        )
    finally:
        logger.removeHandler(caplog.handler)
    record = next(
        record
        for record in caplog.records
        if record.name == "anthropic.managed_agent_poll"
    )
    payload = json.loads(record.message)
    assert payload == {
        "account_scope": True,
        "event": "poll_trace_ready",
        "origin": "https://example.test",
        "path": "/v1/model-work/poll",
        "worker_id": "worker-a",
    }
    assert "synthetic-secret" not in record.message
    assert "password" not in record.message
    assert logging.getLogger("anthropic._base_client").level == logging.WARNING
    assert logging.getLogger("httpx").level == logging.WARNING


def test_managed_agent_poll_trace_installs_info_handler_when_root_filters_it(
    monkeypatch,
) -> None:
    monkeypatch.setenv("MANAGED_AGENT_POLL_TRACE", "true")
    logger = logging.getLogger("anthropic.managed_agent_poll")
    existing = list(logger.handlers)
    try:
        main.configure_managed_agent_poll_trace(
            worker_id="worker-a", base_url="https://example.test"
        )
        assert any(
            getattr(handler, "_managed_agent_poll_trace", False)
            and handler.level <= logging.INFO
            for handler in logger.handlers
        )
    finally:
        logger.handlers[:] = existing


def test_managed_agent_model_trace_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("MANAGED_AGENT_MODEL_TRACE", raising=False)
    logger = logging.getLogger("anthropic.managed_agent_model")
    existing = list(logger.handlers)
    try:
        logger.handlers.clear()
        main.configure_managed_agent_model_trace()
        assert not any(
            getattr(handler, "_managed_agent_model_trace", False)
            for handler in logger.handlers
        )
    finally:
        logger.handlers[:] = existing


def test_managed_agent_model_trace_installs_isolated_handler(monkeypatch) -> None:
    monkeypatch.setenv("MANAGED_AGENT_MODEL_TRACE", "true")
    logger = logging.getLogger("anthropic.managed_agent_model")
    existing = list(logger.handlers)
    try:
        main.configure_managed_agent_model_trace()
        assert logger.propagate is False
        assert any(
            getattr(handler, "_managed_agent_model_trace", False)
            and handler.level <= logging.INFO
            for handler in logger.handlers
        )
        assert logging.getLogger("anthropic._base_client").level == logging.WARNING
        assert logging.getLogger("httpx").level == logging.WARNING
    finally:
        logger.handlers[:] = existing


def test_managed_agent_model_trace_ready_uses_owner_module(monkeypatch, caplog) -> None:
    monkeypatch.setenv("MANAGED_AGENT_MODEL_TRACE", "true")
    logger = logging.getLogger("anthropic.managed_agent_model")
    existing = list(logger.handlers)
    try:
        logger.handlers.clear()
        logger.addHandler(caplog.handler)
        main.configure_managed_agent_model_trace()
        record = next(
            record
            for record in caplog.records
            if record.name == logger.name and "model_trace_ready" in record.message
        )
        payload = json.loads(record.message)
        assert payload["event"] == "model_trace_ready"
        assert payload["module"].endswith("/veadk/models/ark_llm.py")
    finally:
        logger.handlers[:] = existing


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_materialize_session_skills_keeps_pinned_package_files(
    monkeypatch, tmp_path
) -> None:
    calls = []
    session = SimpleNamespace(
        agent=SimpleNamespace(
            skills=[SimpleNamespace(type="custom", skill_id="skill_a", version="v1")]
        )
    )
    client = object()

    async def download(received_client, *, workdir, session):
        calls.append((received_client, Path(workdir), session))
        directory = Path(workdir) / "skills" / "skill-a"
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text("# Pinned instructions")
        return [directory]

    monkeypatch.setattr(resources, "download_session_skills", download)

    resolved = asyncio.run(
        resources.materialize_session_skills(session, tmp_path, client=client)
    )

    assert len(calls) == 1
    assert calls[0][0] is client
    assert calls[0][1].parent == tmp_path.resolve()
    assert calls[0][2] is session
    assert (resolved[0] / "SKILL.md").read_text() == "# Pinned instructions"
    assert "# Pinned instructions" in resources.skill_instructions(resolved)
    asyncio.run(resources.cleanup_session_skills(resolved))


def skill_archive() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("demo/SKILL.md", "# Demo\nRead supporting.txt")
        archive.writestr("demo/supporting.txt", "supporting file marker")
    return buffer.getvalue()


def pinned_session():
    return SimpleNamespace(
        id="session-test",
        agent=SimpleNamespace(
            skills=[SimpleNamespace(skill_id="skill_a", version="v1")]
        ),
    )


@pytest.mark.asyncio
async def test_real_sdk_skill_files_are_readable_isolated_and_cleaned(tmp_path):
    paths = []
    archive = skill_archive()

    def respond(request):
        paths.append(request.url.path)
        if request.url.path.endswith("/content"):
            return httpx2.Response(200, content=archive)
        return httpx2.Response(200, json={"id": "resolved-v1", "name": "demo"})

    async with anthropic.AsyncAnthropic(
        api_key="test-key",
        base_url="https://skills.example.test",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(respond)),
    ) as client:
        first = await resources.materialize_session_skills(
            pinned_session(), tmp_path, client=client
        )
        second = await resources.materialize_session_skills(
            pinned_session(), tmp_path, client=client
        )
    try:
        assert first[0] != second[0]
        assert first[0].is_relative_to(tmp_path)
        assert second[0].is_relative_to(tmp_path)
        assert str(first[0] / "SKILL.md") in resources.skill_instructions(first)
        result = await main._run_managed_tool(
            "read", {"file_path": str(first[0] / "supporting.txt")}, workdir=tmp_path
        )
        assert result["status"] == "completed"
        assert "supporting file marker" in result["stdout"]
        await resources.cleanup_session_skills(first)
        assert not first[0].exists()
        assert (second[0] / "supporting.txt").is_file()
        assert paths.count("/v1/skills/skill_a/versions/resolved-v1/content") == 2
    finally:
        await resources.cleanup_session_skills(first + second)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_real_sdk_interrupted_archive_stream_is_retryable(tmp_path):
    class BrokenStream(httpx2.AsyncByteStream):
        async def __aiter__(self):
            yield b"partial archive"
            raise httpx2.ReadError("connection lost while streaming")

    def respond(request):
        if request.url.path.endswith("/content"):
            return httpx2.Response(200, stream=BrokenStream())
        return httpx2.Response(200, json={"id": "resolved-v1", "name": "demo"})

    async with anthropic.AsyncAnthropic(
        api_key="test-key",
        base_url="https://skills.example.test",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(respond)),
    ) as client:
        with pytest.raises(resources.SessionSkillMaterializationError) as error:
            await resources.materialize_session_skills(
                pinned_session(), tmp_path, client=client
            )
    assert error.value.retryable is True
    assert isinstance(error.value.__cause__, httpx2.ReadError)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["retrieve", "download"])
@pytest.mark.parametrize("failure", ["connection", "timeout", 429, 500, 503, 403, 404])
async def test_real_sdk_skill_failure_retains_retryability(tmp_path, phase, failure):
    def respond(request):
        is_download = request.url.path.endswith("/content")
        if phase == "download" and not is_download:
            return httpx2.Response(200, json={"id": "resolved-v1", "name": "demo"})
        if failure == "connection":
            raise httpx2.ConnectError("connection failed", request=request)
        if failure == "timeout":
            raise httpx2.ReadTimeout("request timed out", request=request)
        return httpx2.Response(failure, json={"error": {"message": "failed"}})

    async with anthropic.AsyncAnthropic(
        api_key="test-key",
        base_url="https://skills.example.test",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(respond)),
    ) as client:
        with pytest.raises(resources.SessionSkillMaterializationError) as error:
            await resources.materialize_session_skills(
                pinned_session(), tmp_path, client=client
            )
    assert error.value.retryable is (failure not in (403, 404))
    assert isinstance(error.value.__cause__, anthropic.APIError)
    assert list(tmp_path.iterdir()) == []


def test_materialize_session_skills_tempfile_default_and_cleanup(
    monkeypatch,
) -> None:
    session = SimpleNamespace(
        id="session-xyz-12345678",
        agent=SimpleNamespace(
            skills=[SimpleNamespace(type="custom", skill_id="skill_b", version="v1")]
        ),
    )

    async def download(client, *, workdir, session):
        directory = Path(workdir) / "skills" / "skill-b"
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text("# Tempfile instructions")
        return [directory]

    monkeypatch.setattr(resources, "download_session_skills", download)

    resolved = asyncio.run(
        resources.materialize_session_skills(session, client=object())
    )

    assert len(resolved) == 1
    temp_root = resolved[0].parents[1]
    assert temp_root in resources._ACTIVE_TEMP_DIRS
    assert temp_root.exists()
    assert (resolved[0] / "SKILL.md").read_text() == "# Tempfile instructions"

    asyncio.run(resources.cleanup_session_skills(resolved))

    assert not temp_root.exists()
    assert temp_root not in resources._ACTIVE_TEMP_DIRS


def test_materialize_session_skills_fails_when_pinned_version_cannot_resolve(
    monkeypatch, tmp_path
) -> None:
    async def download(client, *, workdir, session):
        raise RuntimeError("cannot resolve skill_a@v1")

    monkeypatch.setattr(resources, "download_session_skills", download)
    session = SimpleNamespace(
        agent=SimpleNamespace(
            skills=[SimpleNamespace(skill_id="skill_a", version="v1")]
        )
    )

    with pytest.raises(
        resources.SessionSkillMaterializationError,
        match="failed to materialize pinned Session Skills",
    ) as excinfo:
        asyncio.run(
            resources.materialize_session_skills(session, tmp_path, client=object())
        )
    assert excinfo.value.retryable is False
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert "cannot resolve skill_a@v1" in str(excinfo.value.__cause__)


def test_materialize_session_skills_rejects_partial_sdk_result(
    monkeypatch, tmp_path
) -> None:
    async def download(client, *, workdir, session):
        return []

    monkeypatch.setattr(resources, "download_session_skills", download)
    session = SimpleNamespace(
        agent=SimpleNamespace(
            skills=[SimpleNamespace(skill_id="skill_a", version="v1")]
        )
    )

    with pytest.raises(resources.SessionSkillMaterializationError) as excinfo:
        asyncio.run(
            resources.materialize_session_skills(session, tmp_path, client=object())
        )

    assert excinfo.value.retryable is False
    assert "materialized 0 of 1" in str(excinfo.value.__cause__)


def test_materialize_session_skills_preserves_retryable_transport_failure(
    monkeypatch, tmp_path
) -> None:
    class RetryableError(RuntimeError):
        retryable = True

    async def download(client, *, workdir, session):
        raise RetryableError("temporary transport failure")

    monkeypatch.setattr(resources, "download_session_skills", download)
    session = SimpleNamespace(
        agent=SimpleNamespace(
            skills=[SimpleNamespace(skill_id="skill_a", version="v1")]
        )
    )

    with pytest.raises(resources.SessionSkillMaterializationError) as excinfo:
        asyncio.run(
            resources.materialize_session_skills(session, tmp_path, client=object())
        )

    assert excinfo.value.retryable is True
    assert isinstance(excinfo.value.__cause__, RetryableError)


def test_real_mcp_server_is_restored_from_session_snapshot(tmp_path) -> None:
    port = free_port()
    server = tmp_path / "mcp_server.py"
    server.write_text(
        textwrap.dedent(
            f"""
            from fastmcp import FastMCP
            mcp = FastMCP("managed-session-test")
            @mcp.tool
            def echo_marker(value: str) -> str:
                return "mcp-restored:" + value
            mcp.run(transport="http", host="127.0.0.1", port={port}, path="/mcp", show_banner=False)
            """
        )
    )
    process = subprocess.Popen(
        [sys.executable, str(server)], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        for _ in range(100):
            with socket.socket() as sock:
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.05)
        else:
            raise AssertionError("MCP server did not start")

        snapshot = {
            "mcp_servers": [
                {"type": "url", "name": "echo", "url": f"http://127.0.0.1:{port}/mcp"}
            ],
            "tools": [
                {
                    "type": "mcp_toolset",
                    "mcp_server_name": "echo",
                    "default_config": {
                        "enabled": True,
                        "permission_policy": {"type": "always_allow"},
                    },
                    "configs": [],
                }
            ],
        }
        toolset = resources.mcp_toolsets(snapshot)[0]

        async def use_tool():
            tools = await toolset.get_tools_with_prefix()
            assert [tool.name for tool in tools] == ["mcp__echo__echo_marker"]
            result = await tools[0].run_async(
                args={"value": "ok"}, tool_context=SimpleNamespace(state={})
            )
            await toolset.close()
            return result

        assert "mcp-restored:ok" in str(asyncio.run(use_tool()))
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_custom_tool_waits_for_matching_result_and_resumes() -> None:
    batches = []

    class Page:
        def __aiter__(self):
            async def iterate():
                yield SimpleNamespace(
                    type="user.custom_tool_result",
                    custom_tool_use_id="call-1",
                    content=[{"type": "text", "text": "approved-result"}],
                    is_error=False,
                )

            return iterate()

    async def send(session_id, *, events):
        batches.append((session_id, list(events)))

    sdk = SimpleNamespace(
        beta=SimpleNamespace(
            sessions=SimpleNamespace(
                events=SimpleNamespace(send=send, list=lambda *args, **kwargs: Page())
            )
        )
    )
    tool = main.ManagedCustomTool(
        {
            "type": "custom",
            "name": "approve",
            "description": "Approve",
            "input_schema": {"type": "object"},
        },
        sdk,
        "session-1",
    )
    result = asyncio.run(
        tool.run_async(
            args={"item": "x"},
            tool_context=SimpleNamespace(function_call_id="call-1"),
        )
    )
    assert result == {"result": "approved-result"}
    assert batches[0][1][0]["type"] == "agent.custom_tool_use"
    assert batches[0][1][1]["stop_reason"]["action_type"] == "custom_tool_result"
    assert batches[1][1] == [{"type": "session.status_running"}]


def test_mcp_uses_session_binding_without_mutating_shared_agent():
    snapshot = {
        "model": "model",
        "mcp_servers": [
            {"type": "url", "name": "orders", "url": "https://mcp.example/mcp"}
        ],
        "tools": [{"type": "mcp_toolset", "mcp_server_name": "orders"}],
    }
    refs = [
        {
            "Name": "user-key",
            "PoolName": "team",
            "MCPServerName": "orders",
            "HeaderName": "x-api-key",
            "Prefix": "",
        }
    ]
    config = main.managed_agent_config(snapshot, credential_keys=refs)
    headers = config["tools"][0].identity_headers
    assert headers.name == "user-key" and headers.pool_name == "team"
    assert headers.header == "x-api-key" and headers.prefix == ""
    assert "authorization" not in snapshot["mcp_servers"][0]
    other = main.managed_agent_config(
        snapshot, credential_keys=[{**refs[0], "Name": "other-key"}]
    )
    assert other["tools"][0].identity_headers.name == "other-key"
    assert headers.name == "user-key"
    assert main.managed_agent_config(snapshot)["tools"][0].identity_headers is None
    with pytest.raises(ValueError, match="binding"):
        main.managed_agent_config(
            snapshot, credential_keys=[{**refs[0], "MCPServerName": "unknown"}]
        )
    with pytest.raises(ValueError, match="binding"):
        main.managed_agent_config(snapshot, credential_keys=refs + refs)


def test_session_workdir_rejects_colliding_unsafe_ids(tmp_path):
    with pytest.raises(ValueError):
        resources.session_workdir(tmp_path, "a/b")
    assert resources.session_workdir(tmp_path, "a_b") == tmp_path / "sessions" / "a_b"


@pytest.mark.asyncio
async def test_skill_cleanup_does_not_follow_replaced_directory_symlink(tmp_path):
    root = tmp_path / "owned"
    skill = root / "skills" / "skill"
    skill.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "keep"
    marker.write_text("preserve")
    resources._ACTIVE_TEMP_DIRS.add(root)
    skill.rmdir()
    skill.symlink_to(outside, target_is_directory=True)
    await resources.cleanup_session_skills([skill])
    assert marker.read_text() == "preserve"
    assert not root.exists()
    assert root not in resources._ACTIVE_TEMP_DIRS
