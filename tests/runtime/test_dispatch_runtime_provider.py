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

from types import SimpleNamespace

import pytest
from google.adk.tools import FunctionTool

from veadk.runtime import DispatchRuntimeProvider


def _tool_context():
    return SimpleNamespace(
        function_call_id="call-123",
        _invocation_context=SimpleNamespace(session=SimpleNamespace(id="session-123")),
    )


@pytest.mark.asyncio
async def test_dispatch_runtime_intercepts_configured_tool():
    local_calls = []
    dispatched_calls = []

    def bash(command: str):
        local_calls.append(command)
        return {"source": "local"}

    async def dispatch(tool_call):
        dispatched_calls.append(tool_call)
        return {"source": "remote", "stdout": "ok"}

    provider = DispatchRuntimeProvider(dispatch, dispatchable_tools={"bash"})
    result = await provider.before_tool_callback(
        tool=FunctionTool(bash),
        tool_args={"command": "echo ok"},
        tool_context=_tool_context(),
    )

    assert result == {"source": "remote", "stdout": "ok"}
    assert local_calls == []
    assert len(dispatched_calls) == 1
    assert dispatched_calls[0].name == "bash"
    assert dispatched_calls[0].arguments == {"command": "echo ok"}
    assert dispatched_calls[0].id == "call-123"
    assert dispatched_calls[0].session_id == "session-123"


@pytest.mark.asyncio
async def test_dispatch_runtime_falls_back_to_original_tool():
    local_calls = []

    def read_file(path: str):
        local_calls.append(path)
        return {"content": "local content"}

    provider = DispatchRuntimeProvider(
        lambda tool_call: {"unexpected": tool_call.name},
        dispatchable_tools={"bash"},
    )
    result = await provider.before_tool_callback(
        tool=FunctionTool(read_file),
        tool_args={"path": "/tmp/example"},
        tool_context=_tool_context(),
    )

    assert result == {"content": "local content"}
    assert local_calls == ["/tmp/example"]


@pytest.mark.asyncio
async def test_dispatch_runtime_wraps_scalar_result():
    def bash(command: str):
        raise AssertionError(f"local bash must not run: {command}")

    provider = DispatchRuntimeProvider(lambda tool_call: "remote output")
    result = await provider.before_tool_callback(
        tool=FunctionTool(bash),
        tool_args={"command": "pwd"},
        tool_context=_tool_context(),
    )

    assert result == {"result": "remote output"}


@pytest.mark.asyncio
async def test_dispatch_all_keeps_mcp_tools_on_local_runtime():
    local_calls = []
    dispatched_calls = []

    def call_remote_service(value: str):
        local_calls.append(value)
        return {"source": "mcp"}

    class FakeMcpTool(FunctionTool):
        pass

    provider = DispatchRuntimeProvider(
        lambda tool_call: dispatched_calls.append(tool_call),
        dispatchable_tools=None,
    )
    result = await provider.before_tool_callback(
        tool=FakeMcpTool(call_remote_service),
        tool_args={"value": "hello"},
        tool_context=_tool_context(),
    )

    assert result == {"source": "mcp"}
    assert local_calls == ["hello"]
    assert dispatched_calls == []
