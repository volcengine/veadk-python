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
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from frontend.server.workspace_projects import (
    PersistentWorkspaceProjects,
    owner_session_key,
)
from frontend.server.sandbox_remote import SandboxRemoteTransport
from veadk.cli.frontend_sandbox import SandboxCloudSession, SandboxCloudSnapshot


def cloud(owner="alice"):
    return SandboxCloudSession(
        tool_id="tool",
        instance_id="session",
        endpoint="https://sandbox.test/",
        user_session_id=owner_session_key("tool", owner),
        status="Ready",
        created_by=owner,
        agent_kind="studio-workspace",
        expire_at="2099-01-01T00:00:00Z",
    )


def gateway():
    remote = AsyncMock()
    remote.list_sessions.return_value = []
    remote.list_snapshots.return_value = []
    remote.get_tool.return_value = SimpleNamespace(enable_snapshot=True)
    remote.get_session.return_value = cloud()

    async def create(*args, **kwargs):
        remote.list_sessions.return_value = [cloud()]
        return SimpleNamespace(session_id="session")

    remote._call.side_effect = create
    return remote


@pytest.mark.asyncio
async def test_two_concurrent_projects_share_one_owner_session(monkeypatch):
    remote = gateway()
    service = PersistentWorkspaceProjects(remote, "tool")
    monkeypatch.setattr(
        service, "_projects", AsyncMock(side_effect=[[], ["alpha"], ["alpha", "beta"]])
    )
    monkeypatch.setattr(
        SandboxRemoteTransport, "exec_json", AsyncMock(return_value={"ready": True})
    )
    first, second = await asyncio.gather(
        service.create("alice", "Alice", "alpha"),
        service.create("alice", "Alice", "beta"),
    )
    assert first.instance_id == second.instance_id
    remote._call.assert_awaited_once()
    assert remote._call.call_args.args[1].user_session_id == owner_session_key(
        "tool", "alice"
    )
    session, names = await service.list("alice", "Alice")
    assert names == ["alpha", "beta"] and session == first


@pytest.mark.asyncio
async def test_restarting_studio_reopens_project_without_new_session(monkeypatch):
    remote = gateway()
    remote.list_sessions.return_value = [cloud()]
    service = PersistentWorkspaceProjects(remote, "tool")
    monkeypatch.setattr(service, "_projects", AsyncMock(return_value=["alpha", "beta"]))
    assert await service.open("alice", "Alice", "beta") == cloud()
    remote._call.assert_not_awaited()
    with pytest.raises(HTTPException) as error:
        await service.create("alice", "Alice", "alpha")
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_snapshot_recovery_is_owner_scoped_and_preserves_session_identity(
    monkeypatch,
):
    remote = gateway()
    own = SandboxCloudSnapshot(
        tool_id="tool",
        snapshot_id="saved",
        session_id="old",
        user_session_id=owner_session_key("tool", "alice"),
        status="Ready",
    )
    remote.list_snapshots.return_value = [
        replace(
            own, snapshot_id="foreign", user_session_id=owner_session_key("tool", "bob")
        ),
        own,
    ]
    remote.resume_snapshot.return_value = cloud()
    service = PersistentWorkspaceProjects(remote, "tool")
    monkeypatch.setattr(service, "_projects", AsyncMock(return_value=["alpha", "beta"]))
    assert await service.open("alice", "Alice", "alpha") == cloud()
    remote.resume_snapshot.assert_awaited_once_with(own)
    remote._call.assert_not_awaited()


@pytest.mark.asyncio
async def test_snapshot_not_ready_never_replaces_existing_files():
    remote = gateway()
    remote.list_sessions.return_value = [replace(cloud(), status="Expired")]
    service = PersistentWorkspaceProjects(remote, "tool", recovery_timeout=0)
    with pytest.raises(HTTPException) as error:
        await service.list("alice", "Alice")
    assert error.value.status_code == 504
    remote._call.assert_not_awaited()


@pytest.mark.asyncio
async def test_metadata_mismatch_cannot_expose_another_owners_session():
    remote = gateway()
    remote.list_sessions.return_value = [replace(cloud(), created_by="bob")]
    with pytest.raises(HTTPException) as error:
        await PersistentWorkspaceProjects(remote, "tool").list("alice", "Alice")
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_path_traversal_is_rejected_before_cloud_access():
    remote = gateway()
    with pytest.raises(ValueError):
        await PersistentWorkspaceProjects(remote, "tool").create(
            "alice", "Alice", "../other"
        )
    remote.list_sessions.assert_not_awaited()


@pytest.mark.asyncio
async def test_newer_pending_snapshot_does_not_restore_stale_files():
    remote = gateway()
    old = SandboxCloudSnapshot(
        tool_id="tool",
        snapshot_id="old",
        session_id="old-session",
        user_session_id=owner_session_key("tool", "alice"),
        status="Ready",
        created_at="2026-09-09T01:00:00Z",
    )
    remote.list_snapshots.return_value = [
        old,
        replace(
            old,
            snapshot_id="latest",
            status="Creating",
            created_at="2026-09-09T02:00:00Z",
        ),
    ]
    with pytest.raises(HTTPException) as error:
        await PersistentWorkspaceProjects(remote, "tool", recovery_timeout=0).list(
            "alice", "Alice"
        )
    assert error.value.status_code == 504
    remote.resume_snapshot.assert_not_awaited()
    remote._call.assert_not_awaited()


@pytest.mark.asyncio
async def test_directory_list_ignores_system_folders_and_symlinks(
    monkeypatch, tmp_path
):
    import json
    import shlex
    import subprocess
    import sys

    (tmp_path / "Downloads").mkdir()
    (tmp_path / "alpha" / ".git").mkdir(parents=True)
    (tmp_path / "shortcut").symlink_to(tmp_path / "alpha", target_is_directory=True)

    async def execute(self, command, **kwargs):
        source = shlex.split(command)[2].replace("/home/gem/Projects", str(tmp_path))
        return json.loads(
            subprocess.check_output([sys.executable, "-c", source], text=True)
        )

    monkeypatch.setattr(SandboxRemoteTransport, "exec_json", execute)
    assert await PersistentWorkspaceProjects._projects(cloud()) == ["alpha"]


@pytest.mark.asyncio
async def test_starting_session_is_waited_for_without_creating_another(monkeypatch):
    remote = gateway()
    remote.list_sessions.side_effect = [
        [replace(cloud(), status="Resuming")],
        [cloud()],
    ]
    service = PersistentWorkspaceProjects(remote, "tool")
    monkeypatch.setattr(service, "_projects", AsyncMock(return_value=["alpha"]))
    monkeypatch.setattr("frontend.server.workspace_projects.asyncio.sleep", AsyncMock())
    assert await service.open("alice", "Alice", "alpha") == cloud()
    remote.resume_snapshot.assert_not_awaited()
    remote._call.assert_not_awaited()


@pytest.mark.asyncio
async def test_pending_latest_snapshot_is_awaited_then_restored(monkeypatch):
    remote = gateway()
    snapshot = SandboxCloudSnapshot(
        tool_id="tool",
        snapshot_id="latest",
        session_id="old",
        user_session_id=owner_session_key("tool", "alice"),
        status="Creating",
    )
    saved = replace(snapshot, status="Ready")
    remote.list_snapshots.side_effect = [[snapshot], [saved]]
    remote.resume_snapshot.return_value = cloud()
    service = PersistentWorkspaceProjects(remote, "tool")
    monkeypatch.setattr(service, "_projects", AsyncMock(return_value=["alpha"]))
    monkeypatch.setattr("frontend.server.workspace_projects.asyncio.sleep", AsyncMock())
    assert await service.open("alice", "Alice", "alpha") == cloud()
    remote.resume_snapshot.assert_awaited_once_with(saved)
    remote._call.assert_not_awaited()


@pytest.mark.asyncio
async def test_state_is_read_only_and_cannot_return_another_owners_session():
    remote = gateway()
    remote.list_sessions.return_value = [
        cloud("bob"),
        replace(cloud(), status="Expired"),
    ]
    assert (await PersistentWorkspaceProjects(remote, "tool").state("alice"))[
        "status"
    ] == "sleeping"
    remote.resume_snapshot.assert_not_awaited()
    remote._call.assert_not_awaited()


@pytest.mark.asyncio
async def test_open_renews_session_below_one_hour(monkeypatch):
    from datetime import datetime, timedelta, timezone

    remote = gateway()
    before = replace(
        cloud(),
        expire_at=(datetime.now(timezone.utc) + timedelta(minutes=59)).isoformat(),
    )
    remote.list_sessions.return_value = [before]

    async def renew(action, request, **kwargs):
        assert action == "set_session_ttl"
        assert request.tool_id == "tool" and request.session_id == "session"
        assert request.ttl == 28800 and request.ttl_unit == "second"
        remote.list_sessions.return_value = [cloud()]
        return SimpleNamespace(expire_at=cloud().expire_at)

    remote._call.side_effect = renew
    service = PersistentWorkspaceProjects(remote, "tool")
    monkeypatch.setattr(service, "_projects", AsyncMock(return_value=["alpha"]))
    first, second = await asyncio.gather(
        service.open("alice", "Alice", "alpha"), service.open("alice", "Alice", "alpha")
    )
    assert first.expire_at == second.expire_at == cloud().expire_at
    remote._call.assert_awaited_once()


@pytest.mark.asyncio
async def test_project_metadata_counts_sources_and_keeps_creation_time(
    monkeypatch, tmp_path
):
    import json
    import shlex
    import subprocess
    import sys

    project = tmp_path / "alpha"
    project.mkdir()
    for name in (".git", ".venv", "src"):
        (project / name).mkdir()
    (project / ".git" / "studio-created-at").write_text("1700000000")
    (project / ".venv" / "dependency.py").write_text("")
    (project / "main.py").write_text("")
    (project / "src" / "agent.py").write_text("")
    (project / "external").symlink_to(tmp_path, target_is_directory=True)

    async def execute(self, command, **kwargs):
        script = shlex.split(command)[2].replace("/home/gem/Projects", str(tmp_path))
        result = subprocess.run(
            [sys.executable, "-c", script], check=True, capture_output=True, text=True
        )
        return json.loads(result.stdout)

    monkeypatch.setattr(SandboxRemoteTransport, "exec_json", execute)
    items = await PersistentWorkspaceProjects.describe(cloud(), ["alpha"])
    assert items == [
        {
            "name": "alpha",
            "fileCount": 2,
            "directoryCount": 1,
            "createdAt": "2023-11-14T22:13:20+00:00",
        }
    ]
