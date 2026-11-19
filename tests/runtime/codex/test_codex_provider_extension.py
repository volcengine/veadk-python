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

"""The host-supplied Codex provider endpoint and its runtime wiring."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import tomllib
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from veadk.runtime.codex.config import CodexRuntimeConfig
from veadk.runtime.codex.provider_extension import CodexProviderEndpoint
from veadk.runtime.codex.provider_extension import validate_provider_endpoint
from veadk.runtime.codex.provider_extension import wrap_provider_executors


def _provider(agent: object, context: object) -> object:
    return agent, context


def test_endpoint_defaults_and_aliases_keep_the_key_out_of_repr() -> None:
    endpoint = CodexProviderEndpoint("https://provider.example/v1", "invocation-token")

    assert endpoint.base_url == endpoint.api_base == "https://provider.example/v1"
    assert endpoint.token == endpoint.api_key == "invocation-token"
    assert endpoint.handles_extra_body is False
    assert endpoint.wrap_tool_executor is None
    assert "invocation-token" not in repr(endpoint)


@pytest.mark.parametrize(
    "base",
    [
        "http://127.0.0.1:8123/v1",
        "http://localhost/v1",
        "http://[::1]:8123/v1",
        "https://provider.example/v1",
        "https://provider.example:8443/v1/responses",
    ],
)
def test_endpoint_accepts_loopback_http_and_https_anywhere(base: str) -> None:
    assert CodexProviderEndpoint(base, "token").api_base == base


@pytest.mark.parametrize(
    "base",
    [
        "",
        "provider.example/v1",
        "http://provider.example/v1",
        "ftp://provider.example/v1",
        "https://user:pass@provider.example/v1",
        "https://provider.example/v1?token=leak",
        "https://provider.example/v1#fragment",
        "https://provider.example:0/v1",
        "https://provider.example:not-a-port/v1",
        "https://[::1/v1",
        "https://provider.example/v1\nX-Injected: 1",
    ],
)
def test_endpoint_rejects_unsafe_bases(base: str) -> None:
    with pytest.raises(ValueError):
        CodexProviderEndpoint(base, "token")


@pytest.mark.parametrize("key", ["", "token\nX-Injected: 1", "token\x00"])
def test_endpoint_rejects_unusable_keys(key: str) -> None:
    with pytest.raises(ValueError):
        CodexProviderEndpoint("https://provider.example/v1", key)


def test_endpoint_validates_optional_hooks() -> None:
    with pytest.raises(ValueError):
        CodexProviderEndpoint(
            "https://provider.example/v1", "token", handles_extra_body=1
        )
    with pytest.raises(ValueError):
        CodexProviderEndpoint(
            "https://provider.example/v1", "token", wrap_tool_executor="not-callable"
        )


def test_config_defaults_preserve_shell_access() -> None:
    config = CodexRuntimeConfig()

    assert config.provider_factory is None
    assert config.shell_enabled is True


def test_config_accepts_a_provider_factory_and_keeps_its_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = CodexRuntimeConfig(provider_factory=_provider, shell_enabled=False)

    assert config.provider_factory is _provider
    assert config.model_copy(deep=True).provider_factory is _provider
    # `from_agent` round-trips through model_dump when an environment override
    # is present; the callable must survive that path.
    agent = SimpleNamespace(codex_runtime_config=config)
    monkeypatch.setenv("VEADK_CODEX_THREAD_MODE", "ephemeral")
    resolved = CodexRuntimeConfig.from_agent(agent)
    assert resolved.provider_factory is _provider
    assert resolved.thread_mode == "ephemeral"


def test_config_rejects_unenforceable_or_conflicting_provider_modes() -> None:
    with pytest.raises(ValidationError):
        CodexRuntimeConfig(provider_factory="not-callable")
    with pytest.raises(ValidationError):
        CodexRuntimeConfig(shell_enabled=False)
    with pytest.raises(ValidationError):
        CodexRuntimeConfig(provider_factory=_provider, model_transport="shim")


def test_provider_executor_wrapping_is_optional_and_explicit() -> None:
    raw = {"lookup": object()}
    endpoint = CodexProviderEndpoint("https://provider.example/v1", "token")
    assert wrap_provider_executors(endpoint, raw) is raw

    calls: list[tuple[str, object]] = []

    def wrap(name: str, executor: object) -> Any:
        calls.append((name, executor))

        async def execute(arguments: object, call_id: object) -> str:
            return "wrapped"

        return execute

    endpoint = CodexProviderEndpoint(
        "https://provider.example/v1", "token", wrap_tool_executor=wrap
    )
    wrapped = wrap_provider_executors(endpoint, raw)
    assert wrapped is not raw
    assert calls == [("lookup", raw["lookup"])]
    assert asyncio.run(wrapped["lookup"]({}, "call-1")) == "wrapped"


def test_provider_executor_wrapping_rejects_a_non_callable_result() -> None:
    endpoint = CodexProviderEndpoint(
        "https://provider.example/v1",
        "token",
        wrap_tool_executor=lambda name, executor: None,
    )
    with pytest.raises(TypeError):
        wrap_provider_executors(endpoint, {"lookup": object()})


def test_runtime_requires_the_documented_endpoint_type() -> None:
    with pytest.raises(TypeError):
        validate_provider_endpoint(
            SimpleNamespace(api_base="https://provider.example/v1", api_key="token")
        )
    endpoint = CodexProviderEndpoint("https://provider.example/v1", "token")
    assert validate_provider_endpoint(endpoint) is endpoint


# --------------------------------------------------------------- runtime


class _FakeTurn:
    id = "turn-provider"

    def stream(self) -> Any:
        return _EmptyStream()

    async def interrupt(self) -> None:
        return None


class _EmptyStream:
    def __aiter__(self) -> Any:
        return self

    async def __anext__(self) -> Any:
        raise StopAsyncIteration


class _FakeThread:
    async def turn(self, input_items: list[object], **kwargs: object) -> _FakeTurn:
        return _FakeTurn()


class _FakeAsyncCodex:
    calls: dict[str, Any] = {}
    thread_config: dict[str, Any] | None = None

    def __init__(self, *, config: object) -> None:
        self.calls["config"] = config

    async def __aenter__(self) -> "_FakeAsyncCodex":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def thread_start(self, **kwargs: Any) -> _FakeThread:
        self.calls["thread_start"] = kwargs
        self.thread_config = kwargs.get("config")
        # The runtime removes its private CODEX_HOME when the invocation ends,
        # so capture the generated file while the turn is still running.
        home = self.calls["config"].env["CODEX_HOME"]
        with open(f"{home}/config.toml", "rb") as handle:
            self.calls["home_config"] = tomllib.load(handle)
        return _FakeThread()


class _Context(SimpleNamespace):
    def _get_events(self, **kwargs: object) -> list[object]:
        return list(self.session.events)

    def increment_llm_call_count(self) -> None:
        self.llm_call_count = getattr(self, "llm_call_count", 0) + 1


class _Agent:
    name = "provider-agent"
    description = "Provider contract agent"
    instruction = "Use only allowed tools."
    static_instruction = None
    global_instruction = None
    skills: list[object] = []
    tools: list[object] = []
    model_name = "provider-model"
    model_api_base = "https://backend.invalid/v1"
    model_api_key = "backend-secret"
    model_extra_config: dict[str, object] = {}
    codex_runtime_config = CodexRuntimeConfig()


@pytest.mark.asyncio
async def test_runtime_enters_provider_and_points_codex_at_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    pytest.importorskip("openai_codex")
    from google.genai import types
    from google.adk.events.event import Event
    from google.adk.sessions.session import Session

    from veadk.runtime.codex import runtime as runtime_module

    lifecycle: list[str] = []
    wrapped: list[str] = []

    def wrap_tool_executor(name: str, executor: Any) -> Any:
        wrapped.append(name)

        async def execute(arguments: object, call_id: object) -> str:
            return "wrapped"

        return execute

    @asynccontextmanager
    async def factory(agent: object, context: object):
        assert agent is runtime_agent
        assert context is ctx
        lifecycle.append("enter")
        try:
            yield CodexProviderEndpoint(
                "http://127.0.0.1:1/v1",
                "provider-token",
                handles_extra_body=True,
                wrap_tool_executor=wrap_tool_executor,
            )
        finally:
            lifecycle.append("exit")

    def lookup(query: str) -> str:
        """Look something up."""
        return query

    runtime_agent = _Agent()
    runtime_agent.tools = [lookup]
    runtime_agent.codex_runtime_config = CodexRuntimeConfig(
        provider_factory=factory,
        shell_enabled=False,
        model_transport="direct",
        thread_mode="ephemeral",
        workspace_root=str(tmp_path),
    )
    ctx = _Context(
        invocation_id="inv-provider",
        agent=runtime_agent,
        branch=None,
        isolation_scope=None,
        user_content=types.Content(role="user", parts=[types.Part(text="hello")]),
        session=Session(
            id="session-provider",
            appName="app",
            userId="user",
            state={},
            events=[],
        ),
    )

    async def no_shim(*args: object, **kwargs: object) -> object:
        raise AssertionError("a provider endpoint must not use the shim")

    monkeypatch.setattr(runtime_module, "get_shim", no_shim)
    monkeypatch.setattr(runtime_module, "AsyncCodex", _FakeAsyncCodex)
    monkeypatch.setattr(
        runtime_module, "sync_skills_to_codex_home", lambda *_, **__: None
    )
    _FakeAsyncCodex.calls = {}

    events = [
        event
        async for event in runtime_module.CodexRuntime().run_async(runtime_agent, ctx)
    ]

    assert lifecycle == ["enter", "exit"]
    assert wrapped == ["lookup"]
    assert isinstance(events[-1], Event)
    sdk_config = _FakeAsyncCodex.calls["config"]
    assert sdk_config.env["VEADK_CODEX_MODEL_API_KEY"] == "provider-token"
    thread_config = _FakeAsyncCodex.calls["thread_start"]["config"]
    provider = thread_config["model_providers"]["veadk_direct"]
    assert provider["base_url"] == "http://127.0.0.1:1/v1"
    assert provider["wire_api"] == "responses"
    home = _FakeAsyncCodex.calls["home_config"]
    assert home["model_providers"]["veadk_direct"]["base_url"] == (
        "http://127.0.0.1:1/v1"
    )


@pytest.mark.asyncio
async def test_runtime_does_not_exit_a_provider_that_never_entered(
    tmp_path: Any,
) -> None:
    pytest.importorskip("openai_codex")
    from google.genai import types
    from google.adk.sessions.session import Session

    from veadk.runtime.codex import runtime as runtime_module

    class _Refusing:
        exits = 0

        async def __aenter__(self) -> object:
            raise RuntimeError("provider refused")

        async def __aexit__(self, *exc: object) -> None:
            type(self).exits += 1

    agent = _Agent()
    agent.codex_runtime_config = CodexRuntimeConfig(
        provider_factory=lambda _agent, _context: _Refusing(),
        model_transport="direct",
        workspace_root=str(tmp_path),
    )
    ctx = _Context(
        invocation_id="inv-provider-refused",
        agent=agent,
        branch=None,
        isolation_scope=None,
        user_content=types.Content(role="user", parts=[types.Part(text="hello")]),
        session=Session(
            id="session-provider-refused",
            appName="app",
            userId="user",
            state={},
            events=[],
        ),
    )

    with pytest.raises(RuntimeError, match="provider refused"):
        _ = [
            event async for event in runtime_module.CodexRuntime().run_async(agent, ctx)
        ]
    assert _Refusing.exits == 0


def _agent_and_context(tmp_path: Any, *, name: str, config: CodexRuntimeConfig):
    from google.genai import types
    from google.adk.sessions.session import Session

    agent = _Agent()
    agent.codex_runtime_config = config
    ctx = _Context(
        invocation_id=f"inv-{name}",
        agent=agent,
        branch=None,
        isolation_scope=None,
        user_content=types.Content(role="user", parts=[types.Part(text="hello")]),
        session=Session(
            id=f"session-{name}",
            appName="app",
            userId="user",
            state={},
            events=[],
        ),
    )
    return agent, ctx


@pytest.mark.asyncio
async def test_runtime_requires_an_async_context_manager_from_the_factory(
    tmp_path: Any,
) -> None:
    pytest.importorskip("openai_codex")
    from veadk.runtime.codex import runtime as runtime_module

    agent, ctx = _agent_and_context(
        tmp_path,
        name="provider-not-a-manager",
        config=CodexRuntimeConfig(
            provider_factory=lambda _agent, _context: object(),
            model_transport="direct",
            workspace_root=str(tmp_path),
        ),
    )

    with pytest.raises(TypeError, match="async context manager"):
        _ = [
            event async for event in runtime_module.CodexRuntime().run_async(agent, ctx)
        ]


@pytest.mark.asyncio
async def test_provider_extra_body_warning_keeps_the_provider_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    pytest.importorskip("openai_codex")
    from veadk.runtime.codex import runtime as runtime_module

    async def factory(_agent: object, _context: object) -> Any:
        yield CodexProviderEndpoint(
            "http://127.0.0.1:1/v1", "provider-token", handles_extra_body=False
        )

    factory_cm = asynccontextmanager(factory)
    agent, ctx = _agent_and_context(
        tmp_path,
        name="provider-extra-body",
        config=CodexRuntimeConfig(
            provider_factory=factory_cm,
            model_transport="direct",
            workspace_root=str(tmp_path),
        ),
    )
    agent.model_extra_config = {"extra_body": {"thinking": {"type": "disabled"}}}

    monkeypatch.setattr(runtime_module, "AsyncCodex", _FakeAsyncCodex)
    monkeypatch.setattr(
        runtime_module, "sync_skills_to_codex_home", lambda *_, **__: None
    )
    _FakeAsyncCodex.calls = {}

    with caplog.at_level("WARNING"):
        _ = [
            event async for event in runtime_module.CodexRuntime().run_async(agent, ctx)
        ]

    assert "codex_provider_extra_body_ignored" in caplog.text
    assert (
        _FakeAsyncCodex.calls["thread_start"]["config"]["model_providers"][
            "veadk_direct"
        ]["base_url"]
        == "http://127.0.0.1:1/v1"
    )


@pytest.mark.asyncio
async def test_a_failing_provider_exit_does_not_fail_the_turn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    pytest.importorskip("openai_codex")
    from veadk.runtime.codex import runtime as runtime_module

    class _BrokenExit:
        async def __aenter__(self) -> CodexProviderEndpoint:
            return CodexProviderEndpoint("http://127.0.0.1:1/v1", "provider-token")

        async def __aexit__(self, *exc: object) -> None:
            raise RuntimeError("gateway already gone")

    agent, ctx = _agent_and_context(
        tmp_path,
        name="provider-broken-exit",
        config=CodexRuntimeConfig(
            provider_factory=lambda _agent, _context: _BrokenExit(),
            model_transport="direct",
            workspace_root=str(tmp_path),
        ),
    )

    monkeypatch.setattr(runtime_module, "AsyncCodex", _FakeAsyncCodex)
    monkeypatch.setattr(
        runtime_module, "sync_skills_to_codex_home", lambda *_, **__: None
    )
    _FakeAsyncCodex.calls = {}

    with caplog.at_level("WARNING"):
        events = [
            event async for event in runtime_module.CodexRuntime().run_async(agent, ctx)
        ]

    assert "codex_provider_close_failed" in caplog.text
    assert events


@pytest.mark.asyncio
async def test_tools_setup_failure_closes_the_provider_and_the_toolsets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    pytest.importorskip("openai_codex")
    from veadk.runtime.codex import runtime as runtime_module

    lifecycle: list[str] = []

    async def factory(_agent: object, _context: object) -> Any:
        lifecycle.append("enter")
        try:
            yield CodexProviderEndpoint("http://127.0.0.1:1/v1", "provider-token")
        finally:
            lifecycle.append("exit")

    def lookup(query: str) -> str:
        """Look something up."""
        return query

    agent, ctx = _agent_and_context(
        tmp_path,
        name="provider-tool-setup",
        config=CodexRuntimeConfig(
            provider_factory=asynccontextmanager(factory),
            model_transport="direct",
            thread_mode="ephemeral",
            workspace_root=str(tmp_path),
        ),
    )
    agent.tools = [lookup]

    closed: list[object] = []

    async def broken_resume(bundle: object, context: object) -> list[object]:
        raise RuntimeError("resume failed")

    async def record_close(toolsets: object) -> None:
        closed.append(toolsets)

    monkeypatch.setattr(runtime_module, "resume_authenticated_tools", broken_resume)
    monkeypatch.setattr(runtime_module, "close_toolsets", record_close)

    with pytest.raises(RuntimeError, match="resume failed"):
        _ = [
            event async for event in runtime_module.CodexRuntime().run_async(agent, ctx)
        ]

    assert lifecycle == ["enter", "exit"]
    # The bundle's toolset list is empty for a function tool, but closing it is
    # still the setup-failure contract.
    assert len(closed) == 1


@pytest.mark.asyncio
async def test_runtime_closes_provider_when_setup_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    pytest.importorskip("openai_codex")
    from google.genai import types
    from google.adk.sessions.session import Session

    from veadk.runtime.codex import runtime as runtime_module

    lifecycle: list[str] = []

    @asynccontextmanager
    async def factory(agent: object, context: object):
        lifecycle.append("enter")
        try:
            yield CodexProviderEndpoint("http://127.0.0.1:1/v1", "provider-token")
        finally:
            lifecycle.append("exit")

    agent = _Agent()
    agent.codex_runtime_config = CodexRuntimeConfig(
        provider_factory=factory,
        model_transport="direct",
        workspace_root=str(tmp_path),
    )
    ctx = _Context(
        invocation_id="inv-provider-failure",
        agent=agent,
        branch=None,
        isolation_scope=None,
        user_content=types.Content(role="user", parts=[types.Part(text="hello")]),
        session=Session(
            id="session-provider-failure",
            appName="app",
            userId="user",
            state={},
            events=[],
        ),
    )

    async def broken_bridge() -> object:
        raise RuntimeError("bridge unavailable")

    monkeypatch.setattr(runtime_module, "get_bridge", broken_bridge)

    with pytest.raises(RuntimeError, match="bridge unavailable"):
        _ = [
            event async for event in runtime_module.CodexRuntime().run_async(agent, ctx)
        ]
    assert lifecycle == ["enter", "exit"]
