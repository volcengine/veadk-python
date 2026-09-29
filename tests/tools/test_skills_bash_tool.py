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
import os
import signal
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

bash_module = importlib.import_module("veadk.tools.skills_tools.bash_tool")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(os.name != "posix", reason="POSIX process groups"),
]


@pytest.fixture
def execution(tmp_path, monkeypatch):
    monkeypatch.setattr(bash_module, "get_session_path", lambda **kwargs: tmp_path)
    context = SimpleNamespace(session=SimpleNamespace(id="timeout-test"))
    processes = []
    original = asyncio.create_subprocess_shell

    async def spawn(*args, **kwargs):
        process = await original(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_shell", spawn)

    async def run(command, timeout=5):
        return await bash_module.bash_tool(
            command, "timeout regression", context, timeout
        )

    yield run, processes
    # Independent cleanup also makes a regression failure safe to run locally.
    for process in processes:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def live_group(pgid):
    rows = subprocess.check_output(
        ["ps", "-eo", "pgid=,stat=,comm="], text=True
    ).splitlines()
    return [
        row
        for row in rows
        if row.split()[0] == str(pgid) and not row.split()[1].startswith("Z")
    ]


async def test_pipeline_timeout_cleans_children_and_allows_next_call(execution):
    run, processes = execution
    result = await asyncio.wait_for(run("sleep 900 | cat", timeout=5), 12)
    assert result == "Error: Command timed out after 5s"
    assert not live_group(processes[0].pid)
    assert (
        await asyncio.wait_for(run("echo TOOL_TIMEOUT_RECOVERED"), 7)
        == "TOOL_TIMEOUT_RECOVERED"
    )


async def test_timeout_cleans_group_after_shell_has_already_exited(execution):
    run, processes = execution
    assert (
        await asyncio.wait_for(run("sleep 900 & exit 0", timeout=0.2), 7)
        == "Error: Command timed out after 0.2s"
    )
    assert processes[0].returncode == 0
    assert not live_group(processes[0].pid)


async def test_cancellation_cleans_pipeline_and_propagates(execution):
    run, processes = execution
    task = asyncio.create_task(run("sleep 900 | cat", timeout=600))
    for _ in range(100):
        if processes:
            break
        await asyncio.sleep(0.01)
    assert processes
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 7)
    assert not live_group(processes[0].pid)
    assert await run("echo recovered") == "recovered"


async def test_cancellation_during_spawn_still_cleans_children(execution, monkeypatch):
    run, processes = execution
    spawn = asyncio.create_subprocess_shell
    started = asyncio.Event()
    release = asyncio.Event()

    async def delayed_spawn(*args, **kwargs):
        process = await spawn(*args, **kwargs)
        started.set()
        await release.wait()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_shell", delayed_spawn)
    task = asyncio.create_task(run("sleep 900 | cat", timeout=600))
    await asyncio.wait_for(started.wait(), 3)
    task.cancel()
    await asyncio.sleep(0)
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 7)
    assert not live_group(processes[0].pid)


async def test_cleanup_wait_is_bounded(execution, monkeypatch):
    run, _ = execution

    async def stuck():
        await asyncio.Event().wait()

    process = SimpleNamespace(
        pid=12345,
        communicate=AsyncMock(side_effect=stuck),
        wait=AsyncMock(side_effect=stuck),
        _transport=Mock(),
    )
    monkeypatch.setattr(
        asyncio, "create_subprocess_shell", AsyncMock(return_value=process)
    )
    kill = Mock()
    monkeypatch.setattr(os, "killpg", kill)
    monkeypatch.setattr(bash_module, "_PROCESS_CLEANUP_TIMEOUT", 0.05)
    assert (
        await asyncio.wait_for(run("test", timeout=0.05), 1)
        == "Error: Command timed out after 0.05s"
    )
    kill.assert_called_once_with(process.pid, signal.SIGKILL)
    process._transport.close.assert_called_once()


async def test_process_lookup_race_preserves_timeout(execution, monkeypatch):
    run, _ = execution
    process = SimpleNamespace(
        pid=12345,
        communicate=AsyncMock(side_effect=asyncio.TimeoutError),
        wait=AsyncMock(return_value=0),
    )
    monkeypatch.setattr(
        asyncio, "create_subprocess_shell", AsyncMock(return_value=process)
    )
    monkeypatch.setattr(os, "killpg", Mock(side_effect=ProcessLookupError))
    assert await run("test") == "Error: Command timed out after 5s"
    process.wait.assert_awaited_once()


@pytest.mark.parametrize(
    "command,expected",
    [
        ("", "Error: No command provided"),
        ("printf ok", "ok"),
        ("true", "Command completed successfully."),
        ("printf error >&2; exit 7", "Command failed with exit code 7:\nerror"),
        ("printf output; exit 2", "Command failed with exit code 2:\noutput"),
        ("printf ok; printf WARNING >&2", "ok"),
    ],
)
async def test_output_compatibility(execution, command, expected):
    run, _ = execution
    assert await run(command) == expected


async def test_spawn_failure_is_returned_as_tool_error(execution, monkeypatch):
    run, _ = execution
    monkeypatch.setattr(
        asyncio,
        "create_subprocess_shell",
        AsyncMock(side_effect=OSError("spawn failed")),
    )
    assert await run("test") == "Error executing command 'test': spawn failed"
