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

"""Contract tests for ``LLMShieldPlugin``.

The plugin is wired two ways, and the two wirings disagree: ADK's plugin
manager always ``await``s the hook and passes ``tool_args`` / ``result`` /
``agent``, while the agent callback path awaits only if the hook returns an
awaitable and passes ``args`` / ``tool_response``. These tests pin both calling
conventions, keep the blocking moderation request off the event loop, and pin
the fail-open behavior. No test touches the network.
"""

import inspect
import os
import threading
from typing import Any, Dict, List, Optional

import pytest
from google.adk.models import LlmRequest, LlmResponse
from google.adk.plugins import BasePlugin, PluginManager
from google.genai import types

# The module builds `content_safety = LLMShieldPlugin()` at import time and the
# constructor requires the app id to be configured, so set it before importing.
os.environ.setdefault("TOOL_LLM_SHIELD_APP_ID", "test-app-id")

from veadk.tools.builtin_tools import llm_shield  # noqa: E402
from veadk.tools.builtin_tools.llm_shield import (  # noqa: E402
    LLMShieldPlugin,
    content_safety,
)

# The hooks that actually call the moderation service.
MODERATION_HOOKS = [
    "before_model_callback",
    "after_model_callback",
    "before_tool_callback",
    "after_tool_callback",
]

# Every hook the class overrides, including the two no-ops.
ALL_HOOKS = ["before_agent_callback", "after_agent_callback", *MODERATION_HOOKS]

BLOCK_MESSAGE = "Your request has been blocked due to: Prompt Injection."


class _DummyTool:
    name = "dummy_tool"


class _DummyToolContext:
    invocation_id = "invocation-1"
    session = None


def _llm_request() -> LlmRequest:
    return LlmRequest(
        contents=[types.Content(role="user", parts=[types.Part(text="hello")])]
    )


def _llm_response() -> LlmResponse:
    return LlmResponse(
        content=types.Content(role="model", parts=[types.Part(text="hello")])
    )


def _base_plugin_kwargs(hook: str) -> Dict[str, Any]:
    """Build the exact keyword set ``BasePlugin`` declares for ``hook``.

    Read from the installed ADK rather than hardcoded, so this tracks upstream:
    a renamed or added plugin argument fails here instead of silently drifting.
    """
    values = {
        "agent": object(),
        "callback_context": object(),
        "llm_request": _llm_request(),
        "llm_response": _llm_response(),
        "tool": _DummyTool(),
        "tool_args": {"query": "hello"},
        "tool_context": _DummyToolContext(),
        "result": {"output": "hello"},
    }
    params = inspect.signature(getattr(BasePlugin, hook)).parameters
    names = [name for name in params if name != "self"]
    assert names, f"BasePlugin.{hook} declares no arguments"
    return {name: values[name] for name in names}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Fail loudly instead of reaching the LLM Shield endpoint."""

    def _blocked(*args, **kwargs):
        raise AssertionError("tests must not perform HTTP requests")

    monkeypatch.setattr(llm_shield.requests, "post", _blocked)


@pytest.fixture
def plugin() -> LLMShieldPlugin:
    return LLMShieldPlugin()


def _stub_shield(
    monkeypatch,
    plugin: LLMShieldPlugin,
    verdict: Optional[str] = None,
    calls: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Replace the blocking moderation request with a recorded stub."""

    def _fake_request(**kwargs):
        if calls is not None:
            calls.append(kwargs)
        return verdict

    monkeypatch.setattr(plugin, "_request_llm_shield", _fake_request)


def test_content_safety_is_an_adk_plugin():
    assert isinstance(content_safety, LLMShieldPlugin)
    assert isinstance(content_safety, BasePlugin)


@pytest.mark.parametrize("hook", ALL_HOOKS)
def test_hook_is_a_coroutine_function(hook):
    # The plugin manager does a bare `await callback_method(...)`, so a plain
    # `def` hook returning None raises `TypeError: object NoneType can't be
    # used in 'await' expression`.
    assert inspect.iscoroutinefunction(getattr(LLMShieldPlugin, hook))


@pytest.mark.parametrize("hook", ALL_HOOKS)
@pytest.mark.asyncio
async def test_hook_accepts_base_plugin_keywords(plugin, monkeypatch, hook):
    _stub_shield(monkeypatch, plugin)

    assert await getattr(plugin, hook)(**_base_plugin_kwargs(hook)) is None


@pytest.mark.parametrize("hook", ALL_HOOKS)
@pytest.mark.asyncio
async def test_plugin_manager_invokes_hook(plugin, monkeypatch, hook):
    # The `Runner(plugins=[content_safety])` wiring, driven through ADK itself.
    _stub_shield(monkeypatch, plugin)
    manager = PluginManager(plugins=[plugin])

    assert await getattr(manager, f"run_{hook}")(**_base_plugin_kwargs(hook)) is None


@pytest.mark.parametrize("hook", MODERATION_HOOKS)
@pytest.mark.asyncio
async def test_plugin_manager_short_circuits_on_block(plugin, monkeypatch, hook):
    _stub_shield(monkeypatch, plugin, verdict=BLOCK_MESSAGE)
    manager = PluginManager(plugins=[plugin])

    blocked = await getattr(manager, f"run_{hook}")(**_base_plugin_kwargs(hook))

    if hook.endswith("model_callback"):
        assert isinstance(blocked, LlmResponse)
        assert blocked.content.parts[0].text == BLOCK_MESSAGE
    else:
        assert blocked == {"result": BLOCK_MESSAGE}


@pytest.mark.asyncio
async def test_agent_callback_convention_model_hooks(plugin, monkeypatch):
    _stub_shield(monkeypatch, plugin, verdict=BLOCK_MESSAGE)
    callback_context = object()

    # Keyword form used by `base_llm_flow`.
    blocked = await plugin.before_model_callback(
        callback_context=callback_context, llm_request=_llm_request()
    )
    assert isinstance(blocked, LlmResponse)
    assert blocked.content.parts[0].text == BLOCK_MESSAGE
    assert blocked.partial is True

    blocked = await plugin.after_model_callback(
        callback_context=callback_context, llm_response=_llm_response()
    )
    assert isinstance(blocked, LlmResponse)
    assert blocked.content.parts[0].text == BLOCK_MESSAGE
    assert blocked.partial is True

    # Positional form allowed by the `_SingleBeforeModelCallback` type alias.
    blocked = await plugin.before_model_callback(callback_context, _llm_request())
    assert blocked.content.parts[0].text == BLOCK_MESSAGE

    blocked = await plugin.after_model_callback(callback_context, _llm_response())
    assert blocked.content.parts[0].text == BLOCK_MESSAGE


@pytest.mark.asyncio
async def test_agent_callback_convention_tool_hooks(plugin, monkeypatch):
    calls: List[Dict[str, Any]] = []
    _stub_shield(monkeypatch, plugin, verdict=BLOCK_MESSAGE, calls=calls)
    tool = _DummyTool()
    tool_context = _DummyToolContext()

    # `args` / `tool_response`, the names `functions.py` uses for agent callbacks.
    blocked = await plugin.before_tool_callback(
        tool=tool, args={"query": "hello"}, tool_context=tool_context
    )
    assert blocked == {"result": BLOCK_MESSAGE}
    assert calls[-1]["message"] == "query: hello"

    blocked = await plugin.after_tool_callback(
        tool=tool,
        args={"query": "hello"},
        tool_context=tool_context,
        tool_response="tool output",
    )
    assert blocked == {"result": BLOCK_MESSAGE}
    assert calls[-1]["message"] == "tool output"

    # Positional form allowed by the `_SingleBeforeToolCallback` type alias.
    blocked = await plugin.before_tool_callback(tool, {"query": "hello"}, tool_context)
    assert blocked == {"result": BLOCK_MESSAGE}

    blocked = await plugin.after_tool_callback(
        tool, {"query": "hello"}, tool_context, "tool output"
    )
    assert blocked == {"result": BLOCK_MESSAGE}


@pytest.mark.asyncio
async def test_tool_hooks_read_the_plugin_argument_spelling(plugin, monkeypatch):
    calls: List[Dict[str, Any]] = []
    _stub_shield(monkeypatch, plugin, calls=calls)
    tool = _DummyTool()
    tool_context = _DummyToolContext()

    await plugin.before_tool_callback(
        tool=tool, tool_args={"query": "hello"}, tool_context=tool_context
    )
    assert calls[-1]["message"] == "query: hello"

    await plugin.after_tool_callback(
        tool=tool,
        tool_args={"query": "hello"},
        tool_context=tool_context,
        result={"output": "tool output"},
    )
    assert calls[-1]["message"] == "tool output\n"


@pytest.mark.asyncio
async def test_agent_callback_convention_agent_hooks(plugin):
    # The agent path passes only `callback_context`; both hooks stay no-ops.
    assert await plugin.before_agent_callback(callback_context=object()) is None
    assert await plugin.after_agent_callback(callback_context=object()) is None


@pytest.mark.parametrize("hook", MODERATION_HOOKS)
@pytest.mark.asyncio
async def test_moderation_request_runs_off_the_event_loop(plugin, monkeypatch, hook):
    # `_request_llm_shield` is a blocking `requests.post` with a 50s default
    # timeout, fired up to four times per turn: it must not stall the loop.
    loop_thread = threading.get_ident()
    request_threads: List[int] = []

    def _fake_request(**kwargs):
        request_threads.append(threading.get_ident())
        return None

    monkeypatch.setattr(plugin, "_request_llm_shield", _fake_request)

    await getattr(plugin, hook)(**_base_plugin_kwargs(hook))

    assert request_threads, "the moderation request was never made"
    assert request_threads[0] != loop_thread


@pytest.mark.parametrize("hook", MODERATION_HOOKS)
@pytest.mark.asyncio
async def test_fail_open_when_moderation_returns_none(plugin, monkeypatch, hook):
    # `None` from the shield means "proceed", including on error or timeout.
    calls: List[Dict[str, Any]] = []
    _stub_shield(monkeypatch, plugin, verdict=None, calls=calls)

    assert await getattr(plugin, hook)(**_base_plugin_kwargs(hook)) is None
    assert calls, "the moderation request was never made"
