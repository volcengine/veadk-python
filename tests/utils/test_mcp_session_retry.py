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

from unittest.mock import AsyncMock

import pytest

from veadk.utils.patches import (
    _is_dead_mcp_session,
    _retry_once_on_dead_mcp_session,
    patch_mcp_session_retry,
)


class BrokenResourceError(Exception):
    pass


@pytest.mark.parametrize(
    "error, dead",
    [
        (RuntimeError("Session terminated"), True),
        (RuntimeError("Invalid session ID: abc"), True),
        (ConnectionError("boom"), True),
        (BrokenResourceError("x"), True),
        (ValueError("bad argument"), False),
    ],
)
def test_is_dead_session(error, dead):
    assert _is_dead_mcp_session(error) is dead


class _Fake:
    """Minimal stand-in exposing `_mcp_session_manager` like McpTool/McpToolset."""

    def __init__(self, fail_times):
        self._fail_times = fail_times
        self.calls = 0
        self._mcp_session_manager = AsyncMock()

    async def run(self, *args, **kwargs):
        self.calls += 1
        if self.calls <= self._fail_times:
            raise RuntimeError("Session terminated")
        return "ok"


@pytest.mark.asyncio
async def test_retry_reconnects_and_succeeds():
    wrapped = _retry_once_on_dead_mcp_session(_Fake.run)
    obj = _Fake(fail_times=1)
    assert await wrapped(obj) == "ok"
    assert obj.calls == 2  # failed once, retried once
    obj._mcp_session_manager.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_dead_error_not_retried():
    async def boom(self, *a, **k):
        raise ValueError("nope")

    wrapped = _retry_once_on_dead_mcp_session(boom)
    obj = _Fake(fail_times=0)
    with pytest.raises(ValueError):
        await wrapped(obj)
    obj._mcp_session_manager.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_only_once_then_reraises():
    wrapped = _retry_once_on_dead_mcp_session(_Fake.run)
    obj = _Fake(fail_times=2)  # fails on both attempts
    with pytest.raises(RuntimeError, match="Session terminated"):
        await wrapped(obj)
    assert obj.calls == 2  # original + one retry, no more


def test_apply_patch_idempotent_and_wraps():
    from google.adk.tools.mcp_tool.mcp_tool import McpTool
    from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

    patch_mcp_session_retry()
    patch_mcp_session_retry()  # second call is a no-op
    assert McpTool._veadk_mcp_retry_patched is True
    assert McpToolset._veadk_mcp_retry_patched is True
    assert hasattr(McpTool._run_async_impl, "__wrapped__")
    assert hasattr(McpToolset.get_tools, "__wrapped__")
