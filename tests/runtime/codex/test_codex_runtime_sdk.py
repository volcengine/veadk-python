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
from types import SimpleNamespace

import pytest
from google.adk.sessions.session import Session
from google.genai import types

pytest.importorskip("openai_codex")

from openai_codex import ApprovalMode, Sandbox  # noqa: E402

from veadk.runtime.codex.config import CodexRuntimeConfig  # noqa: E402
from veadk.runtime.codex.runtime import CodexRuntime  # noqa: E402
from veadk.runtime.codex.runtime import _prepare_workspace  # noqa: E402


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

    assert events == []
    assert shim.registered[0]["invocation_id"] == "inv-sdk"
    assert shim.unregistered == ["opaque-turn-token"]
    sdk_config = _FakeAsyncCodex.calls["config"]
    assert sdk_config.env["VEADK_CODEX_API_KEY"] == "opaque-turn-token"
    assert sdk_config.env["OPENAI_API_KEY"] == ""
    assert (
        _FakeAsyncCodex.calls["thread_start"]["approval_mode"] is ApprovalMode.deny_all
    )
    assert _FakeAsyncCodex.calls["thread_start"]["sandbox"] is Sandbox.workspace_write
    # `base_instructions` *replaces* Codex's 20.9KB built-in system prompt, so
    # the runtime deliberately never sends it; the agent identity rides along
    # with the instruction on the developer channel instead.
    assert "base_instructions" not in _FakeAsyncCodex.calls["thread_start"]
    assert _FakeAsyncCodex.calls["thread_start"]["developer_instructions"] == (
        "Your name is agent.\n\nSDK contract agent\n\nFollow the contract."
    )
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
