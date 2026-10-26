"""Session-bound AIO skills must never execute on the Runtime host."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from veadk import Agent
from veadk.tools.skills_tools.skills_toolset import SkillsToolset


@pytest.fixture(autouse=True)
def isolate_cloud(monkeypatch):
    from veadk.skills import check_skills_callback
    from veadk.tools.skills_tools import aio_sandbox

    def forbidden(*args, **kwargs):
        raise AssertionError("Unit tests must not access cloud or host Skill sources")

    monkeypatch.setattr(check_skills_callback, "load_skills_from_cloud", forbidden)
    monkeypatch.setattr(check_skills_callback, "load_skills_from_directory", forbidden)
    monkeypatch.setattr(aio_sandbox, "create_agentkit_client", forbidden)
    monkeypatch.setattr(aio_sandbox, "ensure_agentkit_session_lease", forbidden)


def context(session_id="s1", state=None):
    session = SimpleNamespace(
        app_name="app",
        user_id="user",
        id=session_id,
        state={} if state is None else state,
    )
    return SimpleNamespace(session=session, state=session.state)


def test_aio_construction_never_loads_host_sources():
    with patch("veadk.skills.check_skills_callback._load_sources") as load:
        agent = Agent(
            name="aio",
            skills_mode="aio_sandbox",
            skills=["/remote/skills"],
            model_api_key="test",
        )
    load.assert_not_called()
    assert any(isinstance(t, SkillsToolset) for t in agent.tools)
    empty = Agent(name="aio", skills_mode="aio_sandbox", model_api_key="test")
    assert any(isinstance(t, SkillsToolset) for t in empty.tools)


def test_aio_rejects_cloud_ids_as_paths():
    with pytest.raises(ValueError, match="absolute"):
        Agent(
            name="aio",
            skills_mode="aio_sandbox",
            skills=["ss-cloud"],
            model_api_key="test",
        )


@pytest.mark.asyncio
async def test_binding_identity_and_reuse(monkeypatch):
    from veadk.tools.skills_tools import aio_sandbox as aio

    monkeypatch.setenv("AGENTKIT_TOOL_ID", "t-test")
    lease = SimpleNamespace(
        tool_id="t-test",
        session_id="physical",
        status="Ready",
        endpoint="https://sandbox/",
        internal_endpoint="",
        expire_at="2099-01-01T00:00:00Z",
    )
    ensure = Mock(return_value=lease)
    client = Mock()
    client.get_session.return_value = lease
    monkeypatch.setattr(aio, "ensure_agentkit_session_lease", ensure)
    monkeypatch.setattr(aio, "create_agentkit_client", lambda: client)
    one, two = context(), context("s2")
    await aio.prepare_aio_sandbox(one)
    await aio.prepare_aio_sandbox(one)
    await aio.prepare_aio_sandbox(two)
    assert ensure.call_count == 2
    assert (
        ensure.call_args_list[0].kwargs["tool_user_session_id"]
        != ensure.call_args_list[1].kwargs["tool_user_session_id"]
    )
    assert set(one.state[aio.STATE_KEY]) == {"tool_id", "session_id", "identity"}
    lease.status = "Failed"
    with pytest.raises(RuntimeError, match="Ready"):
        await aio.prepare_aio_sandbox(one)
    assert ensure.call_count == 2


@pytest.mark.asyncio
async def test_remote_catalog_tools_and_query_are_session_scoped(monkeypatch):
    from veadk.tools.skills_tools import aio_sandbox as aio

    calls = []

    def handler(req):
        calls.append(req)
        if req.url.path == "/v1/skills":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "skills": [
                            {
                                "name": req.url.host,
                                "description": "remote skill",
                                "path": "/workspace/skills/demo/SKILL.md",
                            }
                        ]
                    },
                },
            )
        return httpx.Response(
            200, json={"success": True, "data": {"content": "remote instructions"}}
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        aio.httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(handler), **kw),
    )
    monkeypatch.setattr(
        aio,
        "resolve_endpoint",
        AsyncMock(side_effect=lambda ctx: "https://" + ctx.session.id + "/?route=keep"),
    )
    tools = SkillsToolset({}, "aio_sandbox")
    tools._aio_paths = ["/workspace/skills", "/other"]
    one, two = (
        await tools.get_tools(context("one")),
        await tools.get_tools(context("two")),
    )
    assert {t.name for t in one} == {
        "skills_tool",
        "bash_tool",
        "read_file_tool",
        "write_file_tool",
        "edit_file_tool",
    }
    assert "one" in one[0].description and "two" not in one[0].description
    assert "two" in two[0].description
    assert calls[0].url.params.get_list("path") == ["/workspace/skills", "/other"]
    assert calls[0].url.params["route"] == "keep"
    assert await one[0].func("one") == (
        "Base directory for this skill: /workspace/skills/demo\n\nremote instructions"
    )
    assert calls[-1].url.params["route"] == "keep"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, text="secret-body"),
        httpx.Response(200, json={"success": False, "message": "secret-body"}),
        httpx.Response(200, text="invalid secret-body"),
    ],
)
async def test_transport_errors_redacted_and_not_retried(monkeypatch, response):
    from veadk.tools.skills_tools import aio_sandbox as aio

    seen = []

    def handler(req):
        seen.append(req)
        return response

    original = httpx.AsyncClient
    monkeypatch.setattr(
        aio.httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(handler), **kw),
    )
    with pytest.raises(RuntimeError) as error:
        await aio.Sandbox("https://sandbox/?token=secret").call(
            "POST", "/v1/file/write", {"file": "/test", "content": "x"}
        )
    assert "secret" not in str(error.value)
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_bash_polling_failure_and_cleanup():
    from veadk.tools.skills_tools.aio_sandbox import Sandbox

    sandbox = Sandbox("https://sandbox")
    calls = []

    async def call(method, path, body=None, **kwargs):
        calls.append((path, body))
        if path == "/v1/bash/exec":
            return {
                "status": "running",
                "command_id": "cmd",
                "stdout": "start",
                "offset": 5,
                "stderr_offset": 0,
            }
        if path == "/v1/bash/output":
            return {
                "stdout": "end",
                "stderr": "",
                "offset": 8,
                "stderr_offset": 0,
                "command": {"status": "completed", "exit_code": 0},
            }
        return {}

    sandbox.call = call
    assert await sandbox.bash("echo sandbox", 5) == "startend"
    assert calls[-1][0].endswith("/close")
    assert all("env" not in body for _, body in calls if body)


@pytest.mark.asyncio
async def test_bash_cancellation_kills_and_closes():
    from veadk.tools.skills_tools.aio_sandbox import Sandbox

    sandbox = Sandbox("https://sandbox")
    entered = asyncio.Event()
    calls = []

    async def call(method, path, body=None, **kwargs):
        calls.append(path)
        if path == "/v1/bash/exec":
            entered.set()
            await asyncio.Event().wait()
        return {}

    sandbox.call = call
    task = asyncio.create_task(sandbox.bash("sleep 100", 10))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert "/v1/bash/kill" in calls
    assert calls[-1].endswith("/close")


@pytest.mark.asyncio
async def test_remote_file_contract_and_editor_errors(monkeypatch):
    from veadk.tools.skills_tools import aio_sandbox as aio

    sandbox = aio.Sandbox("https://sandbox")
    calls = []

    async def call(method, path, body=None, **kwargs):
        calls.append((path, body))
        if path == "/v1/skills":
            return {"skills": []}
        if path == "/v1/file/read":
            return {"content": "second\nthird\n"}
        return {"output": "edited"}

    sandbox.call = call
    monkeypatch.setattr(aio, "Sandbox", lambda *args: sandbox)
    monkeypatch.setattr(
        aio, "resolve_endpoint", AsyncMock(return_value="https://sandbox")
    )
    tools = {t.name: t for t in await aio.build_aio_tools(context(), [])}
    assert (
        await tools["read_file_tool"].func("test", 2, 2)
        == "     2|second\n     3|third"
    )
    assert calls[-1] == (
        "/v1/file/read",
        {"file": "/workspace/test", "start_line": 1, "end_line": 3},
    )
    await tools["write_file_tool"].func("test", "contents")
    assert calls[-1] == (
        "/v1/file/write",
        {"file": "/workspace/test", "content": "contents"},
    )
    await tools["edit_file_tool"].func("test", "old", "new", False)
    assert calls[-1][1]["replace_mode"] is None
    await tools["edit_file_tool"].func("test", "old", "new", True)
    assert calls[-1][1]["replace_mode"] == "ALL"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exit_code,status", [(1, "completed"), (None, "timed_out"), (None, "killed")]
)
async def test_bash_terminal_errors_are_not_success(exit_code, status):
    from veadk.tools.skills_tools.aio_sandbox import Sandbox

    sandbox = Sandbox("https://sandbox")

    async def call(method, path, body=None, **kwargs):
        return (
            {"status": status, "exit_code": exit_code}
            if path == "/v1/bash/exec"
            else {}
        )

    sandbox.call = call
    with pytest.raises(RuntimeError, match="AIO bash failed"):
        await sandbox.bash("false", 5)


@pytest.mark.asyncio
async def test_timeout_kills_and_closes_and_cleanup_failures_are_visible():
    from veadk.tools.skills_tools.aio_sandbox import Sandbox

    sandbox = Sandbox("https://sandbox")
    calls = []

    async def call(method, path, body=None, **kwargs):
        calls.append(path)
        if path == "/v1/bash/exec":
            await asyncio.Event().wait()
        return {}

    sandbox.call = call
    with pytest.raises(asyncio.TimeoutError):
        await sandbox.bash("sleep 100", 0.01)
    assert "/v1/bash/kill" in calls and calls[-1].endswith("/close")

    async def failing_close(method, path, body=None, **kwargs):
        if path.endswith("/close"):
            raise RuntimeError("unavailable")
        return {"status": "completed", "exit_code": 0}

    sandbox.call = failing_close
    with pytest.raises(RuntimeError, match="cleanup failed"):
        await sandbox.bash("true", 5)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data",
    [{"skills": [{"name": "bad"}]}, {"skills": None}, {"error": "private details"}],
)
async def test_invalid_catalog_and_editor_failure_never_succeed(monkeypatch, data):
    from veadk.tools.skills_tools import aio_sandbox as aio

    original = httpx.AsyncClient
    monkeypatch.setattr(
        aio.httpx,
        "AsyncClient",
        lambda **kw: original(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, json={"success": True, "data": data})
            ),
            **kw,
        ),
    )
    monkeypatch.setattr(
        aio, "resolve_endpoint", AsyncMock(return_value="https://sandbox")
    )
    with pytest.raises(RuntimeError):
        await aio.build_aio_tools(context(), [])


@pytest.mark.asyncio
async def test_cancellation_during_shell_close_is_preserved():
    from veadk.tools.skills_tools.aio_sandbox import Sandbox

    sandbox = Sandbox("https://sandbox")
    closing = asyncio.Event()
    released = asyncio.Event()
    closed = asyncio.Event()

    async def call(method, path, body=None, **kwargs):
        if path.endswith("/close"):
            closing.set()
            await released.wait()
            closed.set()
        return {"status": "completed", "exit_code": 0}

    sandbox.call = call
    task = asyncio.create_task(sandbox.bash("true", 5))
    await closing.wait()
    task.cancel()
    released.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()


@pytest.mark.asyncio
async def test_api_key_stays_in_headers_and_redirect_is_not_followed(monkeypatch):
    from veadk.tools.skills_tools import aio_sandbox as aio

    monkeypatch.setenv("SANDBOX_API_KEY", "test-sandbox-key")
    headers = await aio._headers(context())
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(302, headers={"location": "https://untrusted/"})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        aio.httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(handler), **kw),
    )
    with pytest.raises(RuntimeError, match="HTTP 302"):
        await aio.Sandbox("https://sandbox/?route=preserved", headers).call(
            "GET", "/v1/skills"
        )
    assert len(calls) == 1
    assert calls[0].headers["x-api-key"] == "test-sandbox-key"
    assert calls[0].url.params["route"] == "preserved"
    assert b"test-sandbox-key" not in calls[0].content
