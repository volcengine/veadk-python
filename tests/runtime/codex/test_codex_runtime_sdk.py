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

"""Contract tests for the optional openai-codex SDK integration."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from google.adk.sessions.session import Session
from google.genai import types

pytest.importorskip("openai_codex")

from openai_codex import ApprovalMode  # noqa: E402

from veadk.runtime.codex.config import CodexRuntimeConfig  # noqa: E402
from veadk.runtime.codex.runtime import CodexRuntime  # noqa: E402
from veadk.runtime.codex.runtime import _TOOL_AVAILABILITY_NOTE  # noqa: E402
from veadk.runtime.codex.runtime import _prepare_workspace  # noqa: E402


def test_existing_empty_workspace_is_not_a_reset(tmp_path):
    from types import SimpleNamespace
    from veadk.runtime.codex.runtime import _prepare_workspace_state

    ctx: Any = SimpleNamespace(
        session=SimpleNamespace(app_name="app", user_id="user", id="session"),
        agent=SimpleNamespace(name="agent"),
    )
    config = CodexRuntimeConfig(workspace_root=str(tmp_path))
    path, created = _prepare_workspace_state(config, ctx)
    assert created
    assert not list(Path(path).iterdir())
    assert _prepare_workspace_state(config, ctx) == (path, False)
    Path(path).rmdir()
    assert _prepare_workspace_state(config, ctx) == (path, True)


def test_mcp_reuse_default_and_environment_override(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.delenv("VEADK_CODEX_MCP_PROCESS_REUSE", raising=False)
    assert CodexRuntimeConfig().mcp_process_reuse
    assert CodexRuntimeConfig.from_agent(SimpleNamespace()).mcp_process_reuse
    assert not CodexRuntimeConfig.from_agent(
        SimpleNamespace(
            codex_runtime_config=CodexRuntimeConfig(mcp_process_reuse=False)
        )
    ).mcp_process_reuse
    monkeypatch.setenv("VEADK_CODEX_MCP_PROCESS_REUSE", "1")
    assert CodexRuntimeConfig.from_agent(SimpleNamespace()).mcp_process_reuse
    monkeypatch.setenv("VEADK_CODEX_MCP_PROCESS_REUSE", "0")
    assert not CodexRuntimeConfig.from_agent(
        SimpleNamespace(codex_runtime_config=CodexRuntimeConfig(mcp_process_reuse=True))
    ).mcp_process_reuse


@pytest.mark.parametrize("value", ["0", "false", "off", "no"])
def test_mcp_reuse_can_be_disabled_by_environment(monkeypatch, value):
    monkeypatch.setenv("VEADK_CODEX_MCP_PROCESS_REUSE", value)
    assert not CodexRuntimeConfig.from_agent(SimpleNamespace()).mcp_process_reuse


class _FakeShim:
    url = "http://127.0.0.1:12345"

    def __init__(self) -> None:
        self.registered = []
        self.unregistered = []

    def register_turn(
        self,
        specs,
        executors,
        *,
        max_tool_iterations=None,
        invocation_id="",
        model_extra_config=None,
        on_model_call=None,
    ):
        # Keyword-only params must carry defaults: the production signature has
        # grown twice, and a required keyword here turns a runtime change into
        # an opaque TypeError in an unrelated test.
        self.registered.append(
            {
                "specs": specs,
                "executors": executors,
                "max_tool_iterations": max_tool_iterations,
                "invocation_id": invocation_id,
                "model_extra_config": model_extra_config,
                "on_model_call": on_model_call,
            }
        )
        return "opaque-turn-token"

    def unregister_turn(self, token):
        self.unregistered.append(token)

    async def close_turn(self, token):
        self.unregister_turn(token)

    def turn_marker(self, token):
        # Mirrors the real shim: an opaque per-turn marker the runtime embeds
        # in the Codex prompt, and "" for a token the shim does not know.
        return "turn-marker" if token == "opaque-turn-token" else ""

    def turn_error(self, token):
        # The real shim reports an exception raised inside it that aborted the
        # turn; nothing fails inside this fake, so there is never one.
        return None


class _EmptyStream:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration

    async def aclose(self):
        return None


class _FakeTurn:
    id = "turn-1"

    def stream(self):
        return _EmptyStream()

    async def interrupt(self):
        return None


class _FakeThread:
    def __init__(self, calls):
        self.calls = calls

    async def turn(self, input_items, **kwargs):
        self.calls["turn"] = {"input": input_items, **kwargs}
        return _FakeTurn()


class _FakeAsyncCodex:
    calls = {}
    raise_on_start = False

    def __init__(self, *, config):
        self.calls["config"] = config

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def thread_start(self, **kwargs):
        if self.raise_on_start:
            raise RuntimeError("sdk start failed")
        self.calls["thread_start"] = kwargs
        return _FakeThread(self.calls)


class _Agent:
    name = "agent"
    description = "SDK contract agent"
    instruction = "Follow the contract."
    static_instruction = None
    global_instruction = None
    tools = []
    skills = []
    model_name = "test-model"
    model_api_base = "https://backend.invalid/v1"
    model_api_key = "backend-secret"
    # `Agent.model_extra_config` is a real field (default_factory=dict), so it
    # is always present on an agent the runtime is handed. The runtime forwards
    # it to `shim.register_turn`; without it here the fake diverges from the
    # production contract and the runtime raises AttributeError before reaching
    # anything this test is about.
    model_extra_config = {}
    codex_runtime_config = CodexRuntimeConfig()


class _Context(SimpleNamespace):
    def _get_events(self, **kwargs):
        return list(self.session.events)

    def increment_llm_call_count(self):
        # Without this attribute the runtime's `max_llm_calls` charging
        # silently no-ops and the SDK contract test covers nothing.
        self.llm_call_count = getattr(self, "llm_call_count", 0) + 1


@pytest.mark.asyncio
async def test_runtime_passes_isolated_config_and_safe_sdk_controls(
    monkeypatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from veadk.runtime.codex import runtime as runtime_module

    shim = _FakeShim()

    async def fake_get_shim(api_base, api_key):
        assert api_base == "https://backend.invalid/v1"
        assert api_key == "backend-secret"
        return shim

    monkeypatch.setattr(runtime_module, "get_shim", fake_get_shim)
    monkeypatch.setattr(runtime_module, "AsyncCodex", _FakeAsyncCodex)
    monkeypatch.setattr(
        runtime_module, "sync_skills_to_codex_home", lambda *_, **__: None
    )
    monkeypatch.setenv("OPENAI_API_KEY", "host-secret")
    _FakeAsyncCodex.calls = {}
    runtime_logger = logging.getLogger("veadk.runtime.codex.runtime")
    runtime_logger.addHandler(caplog.handler)
    runtime_logger.setLevel(logging.DEBUG)

    agent = _Agent()
    user_content = types.Content(role="user", parts=[types.Part(text="hello")])
    ctx = _Context(
        invocation_id="inv-sdk",
        agent=agent,
        branch=None,
        isolation_scope=None,
        user_content=user_content,
        session=Session(
            id="session-sdk",
            appName="app",
            userId="user",
            state={},
            events=[],
        ),
    )

    try:
        events = [event async for event in CodexRuntime().run_async(agent, ctx)]
    finally:
        runtime_logger.removeHandler(caplog.handler)

    # An empty Codex stream still yields exactly one event: the merged
    # per-turn response. After-model callbacks have to run on every turn, and
    # when nothing durable was emitted there is no tool event to fold the
    # `state_delta`/`usage_metadata` bookkeeping onto and nothing for a
    # contentless event to clobber -- so the runtime emits it rather than
    # dropping it (the final `else` in `CodexRuntime.run_async`'s merge).
    assert len(events) == 1, events
    assert events[0].content is None
    assert events[0].author == "agent"
    assert events[0].invocation_id == "inv-sdk"
    assert shim.registered[0]["invocation_id"] == "inv-sdk"
    assert shim.unregistered == ["opaque-turn-token"]
    sdk_config = _FakeAsyncCodex.calls["config"]
    assert sdk_config.env["VEADK_CODEX_API_KEY"] == "opaque-turn-token"
    assert sdk_config.env["OPENAI_API_KEY"] == ""
    assert (
        _FakeAsyncCodex.calls["thread_start"]["approval_mode"] is ApprovalMode.deny_all
    )
    # No preset: it would replace the config's permissions profile.
    assert _FakeAsyncCodex.calls["thread_start"]["sandbox"] is None
    # `base_instructions` *replaces* Codex's 20.9KB built-in system prompt, so
    # the runtime deliberately never sends it; the agent identity rides along
    # with the instruction on the developer channel instead.
    assert "base_instructions" not in _FakeAsyncCodex.calls["thread_start"]
    # Identity, then the agent's instruction, then the runtime's note about the
    # two tools Codex's own prompt gets wrong here (its content is asserted in
    # `test_codex_turn_contract.py`; this row is about ordering and joining).
    assert _FakeAsyncCodex.calls["thread_start"]["developer_instructions"] == (
        "Your name is agent.\n\nSDK contract agent\n\nFollow the contract.\n\n"
        + _TOOL_AVAILABILITY_NOTE
    )
    # `on_model_call` is what makes `RunConfig.max_llm_calls` fire at all for
    # runtime="codex": ADK enforces the budget only through
    # `increment_llm_call_count`, which its own LLM flow -- the one this
    # runtime replaces -- would normally call. The real shim invokes this hook
    # once per backend model call; `_FakeShim` never reaches a backend, so
    # assert the runtime *wired* it and that invoking it charges the context.
    on_model_call = shim.registered[0]["on_model_call"]
    assert on_model_call is not None, "max_llm_calls can never fire for this runtime"
    assert not hasattr(ctx, "llm_call_count")
    on_model_call()
    assert ctx.llm_call_count == 1, "the invocation was never charged an LLM call"
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "codex_runtime_start invocation_id=inv-sdk" in messages
    assert "codex_runtime_complete invocation_id=inv-sdk status=completed" in messages
    assert "backend-secret" not in messages
    assert "host-secret" not in messages
    assert "opaque-turn-token" not in messages


@pytest.mark.asyncio
async def test_runtime_unregisters_turn_when_sdk_start_fails(monkeypatch) -> None:
    from veadk.runtime.codex import runtime as runtime_module

    shim = _FakeShim()

    async def fake_get_shim(api_base, api_key):
        return shim

    monkeypatch.setattr(runtime_module, "get_shim", fake_get_shim)
    monkeypatch.setattr(runtime_module, "AsyncCodex", _FakeAsyncCodex)
    monkeypatch.setattr(
        runtime_module, "sync_skills_to_codex_home", lambda *_, **__: None
    )
    _FakeAsyncCodex.calls = {}
    _FakeAsyncCodex.raise_on_start = True

    agent = _Agent()
    ctx = _Context(
        invocation_id="inv-failed-sdk",
        agent=agent,
        branch=None,
        isolation_scope=None,
        user_content=types.Content(role="user", parts=[types.Part(text="hello")]),
        session=Session(
            id="session-sdk-failure",
            appName="app",
            userId="user",
            state={},
            events=[],
        ),
    )

    try:
        with pytest.raises(RuntimeError, match="sdk start failed"):
            _ = [event async for event in CodexRuntime().run_async(agent, ctx)]
    finally:
        _FakeAsyncCodex.raise_on_start = False

    assert shim.unregistered == ["opaque-turn-token"]


def test_session_workspaces_are_stable_and_isolated(tmp_path) -> None:
    agent = _Agent()
    config = CodexRuntimeConfig(workspace_root=str(tmp_path))

    def context(session_id):
        return _Context(
            agent=agent,
            session=Session(
                id=session_id,
                appName="app",
                userId="user",
                state={},
                events=[],
            ),
        )

    first = _prepare_workspace(config, context("session-a"))
    repeated = _prepare_workspace(config, context("session-a"))
    second = _prepare_workspace(config, context("session-b"))

    assert first == repeated
    assert first != second

    # `_prepare_workspace` returns a plain path: the old second tuple element
    # was always False, which made four rmtree call sites dead code. Session
    # workspaces outlive a turn and are reaped on an idle TTL instead.
    assert isinstance(first, str)

    shared_config = CodexRuntimeConfig(
        workspace_root=str(tmp_path / "shared"),
        reuse_workspace=True,
    )
    shared = _prepare_workspace(shared_config, context("session-c"))
    assert shared == str(tmp_path / "shared")


def test_codex_home_pins_settings_the_pinned_cli_would_break(tmp_path) -> None:
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10: pytest depends on tomli there.
        import tomli as tomllib

    from veadk.runtime.codex.model_provider import shim_route
    from veadk.runtime.codex.runtime import _nested_read_access, _prepare_codex_home

    import os
    import tempfile

    workspace = os.path.realpath(tempfile.mkdtemp(prefix="veadk-codex-ws-"))
    home = _prepare_codex_home(
        shim_route("http://127.0.0.1:9", ""),
        "model-x",
        CodexRuntimeConfig(network_access=True),
        workspace=workspace,
    )
    try:
        with open(f"{home}/config.toml", "rb") as f:
            config = tomllib.load(f)
    finally:
        import shutil

        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(workspace, ignore_errors=True)

    # Both default to on in the pinned CLI. Unbounded retries would turn an
    # unreachable shim into a hung invocation (this runtime has no turn
    # timeout), and goals advertise tools that need a persisted thread.
    assert config["features"] == {
        "unbounded_connection_retries": False,
        "goals": False,
    }
    # The CLI otherwise sends `reasoning.summary = "auto"`, which Ark's
    # Responses API rejects outright (`json: unknown field "summary"`).
    assert config["model_reasoning_summary"] == "none"
    # Without an explicit policy the sandboxed shell's `env` showed the model
    # key and turn tokens; see the smoke test for the end-to-end check.
    assert set(config["shell_environment_policy"]["exclude"]) >= {
        "VEADK_CODEX_*",
        "*API_KEY*",
        "*TOKEN*",
    }
    assert config["model_providers"]["veadk"]["wire_api"] == "responses"
    # Sandboxed commands run under VeADK's permissions profile, which Codex
    # rejects next to the legacy sandbox keys.
    assert config["default_permissions"] == "veadk"
    assert "sandbox_mode" not in config and "sandbox_workspace_write" not in config
    profile = config["permissions"]["veadk"]
    assert profile["network"]["enabled"] is True
    assert profile["extends"] == ":read-only"
    # Only this session's workspace is writable, and of CODEX_HOME only its
    # skills are readable; the temp dirs every other session lives in are not.
    tmp = os.path.realpath(tempfile.gettempdir())
    assert profile["filesystem"][tmp] == "deny"
    assert profile["filesystem"][os.path.realpath("/tmp")] == "deny"
    assert profile["filesystem"][workspace] == "write"
    assert profile["filesystem"][os.path.realpath(f"{home}/skills")] == (
        _nested_read_access()
    )
    assert config["shell_environment_policy"]["set"] == {"TMPDIR": workspace}
    # No AGENTS.md search above the workspace, whose parents are denied.
    assert config["project_root_markers"] == []


def test_direct_codex_home_names_the_key_env_var_but_never_holds_the_key() -> None:
    """On the direct transport config.toml points at the backend itself.

    The file lives on disk for the whole invocation, so it may name the env var
    that carries the credential but must never contain the credential.
    """
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10: pytest depends on tomli there.
        import tomli as tomllib
    import shutil
    import tempfile

    from veadk.runtime.codex.model_provider import DIRECT_KEY_ENV
    from veadk.runtime.codex.model_provider import direct_route
    from veadk.runtime.codex.runtime import _prepare_codex_home

    secret = "ark-secret-value-never-on-disk"
    route = direct_route(
        "https://ark.cn-beijing.volces.com/api/v3/",
        secret,
        extra_headers={"X-Client": "veadk"},
    )
    home = _prepare_codex_home(
        route, "model-x", CodexRuntimeConfig(), workspace=tempfile.gettempdir()
    )
    try:
        with open(f"{home}/config.toml", "rb") as f:
            raw = f.read()
        config = tomllib.loads(raw.decode("utf-8"))
    finally:
        shutil.rmtree(home, ignore_errors=True)

    assert secret.encode() not in raw
    assert config["model_provider"] == route.provider_id
    provider = config["model_providers"][route.provider_id]
    assert provider["base_url"] == "https://ark.cn-beijing.volces.com/api/v3"
    assert provider["env_key"] == DIRECT_KEY_ENV
    assert provider["wire_api"] == "responses"
    assert provider["http_headers"] == {"X-Client": "veadk"}


def test_sandbox_profile_denies_configured_host_paths(monkeypatch, tmp_path) -> None:
    """Host files outside the temp dirs can be denied too; the workspace stays."""
    import os

    from veadk.runtime.codex.runtime import _sandbox_profile

    secrets_dir, db = tmp_path / "app", tmp_path / "sessions.db"
    workspace = tmp_path / "app" / "ws"
    monkeypatch.setenv(
        "VEADK_CODEX_DENY_READ_PATHS", os.pathsep.join([str(secrets_dir), str(db)])
    )
    profile = _sandbox_profile(CodexRuntimeConfig(), str(workspace), str(tmp_path))
    assert profile is not None
    filesystem = profile["permissions"]["veadk"]["filesystem"]
    assert filesystem[os.path.realpath(secrets_dir)] == "deny"
    assert filesystem[os.path.realpath(db)] == "deny"
    assert filesystem[os.path.realpath(workspace)] == "write"
    assert (
        _sandbox_profile(
            CodexRuntimeConfig(sandbox="full_access", network_access=True),
            str(workspace),
            str(tmp_path),
        )
        is None
    )


def test_linux_grants_nested_session_paths_write(monkeypatch, tmp_path) -> None:
    """Codex's Linux sandbox cannot reach a `read` grant under a denied parent.

    The session's own workspace (even for `read_only`) and its skills copy are
    granted `write` there instead; everything else stays denied.
    """
    import os

    from veadk.runtime.codex import runtime as runtime_module

    workspace, home = tmp_path / "ws", tmp_path / "home"
    for platform, expected in (("linux", "write"), ("darwin", "read")):
        monkeypatch.setattr(runtime_module.sys, "platform", platform)
        profile = runtime_module._sandbox_profile(
            CodexRuntimeConfig(sandbox="read_only"), str(workspace), str(home)
        )
        assert profile is not None
        filesystem = profile["permissions"]["veadk"]["filesystem"]
        assert filesystem[os.path.realpath(workspace)] == expected
        assert filesystem[os.path.realpath(home / "skills")] == expected
        assert os.path.realpath(home) not in filesystem
