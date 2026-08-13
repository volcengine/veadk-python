from __future__ import annotations

from types import SimpleNamespace

import pytest

from frontend.server.vibe_task.remote_executor import VibeRemoteExecutor


class Store:
    async def find(self, owner, task):
        assert (owner, task) == ("owner", "vt-task")
        return SimpleNamespace(endpoint="https://sandbox")


class Transport:
    command = ""

    def __init__(self, endpoint):
        assert endpoint == "https://sandbox"

    async def exec_json(self, command, *, timeout):
        self.__class__.command = command
        assert timeout == 20
        return {"exitCode": 0, "stdout": "ok", "stderr": ""}


@pytest.mark.asyncio
async def test_executor_uses_typed_argv_and_task_workspace(monkeypatch) -> None:
    monkeypatch.setattr(
        "frontend.server.vibe_task.remote_executor.SandboxRemoteTransport", Transport
    )
    result = await VibeRemoteExecutor(Store())(
        "owner", "vt-task", ("python", "-V"), "/home/gem/workspace/vt-task", 10
    )
    assert result.succeeded
    assert "subprocess.run(argv" in Transport.command
    assert "shell=True" not in Transport.command


@pytest.mark.asyncio
async def test_executor_rejects_foreign_workspace() -> None:
    with pytest.raises(ValueError, match="task workspace"):
        await VibeRemoteExecutor(Store())(
            "owner", "vt-task", ("python", "-V"), "/tmp", 10
        )
