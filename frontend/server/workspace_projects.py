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

"""One recoverable cloud Sandbox per owner, with projects as directories."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shlex
from dataclasses import replace
from datetime import datetime, timezone

from agentkit.sdk.tools.types import SetSessionTtlRequest
from typing import Any

from fastapi import HTTPException

from frontend.server.sandbox_remote import SandboxRemoteTransport
from frontend.server.workspace_preview import ProjectInput, _expired
from veadk.cli.agentkit_session_metadata import build_create_session_request
from veadk.cli.frontend_sandbox import SandboxCloudSession, STUDIO_SANDBOX_TTL_SECONDS

_KIND = "studio-workspace"
_TRANSITIONAL_SESSIONS = {
    "creating",
    "starting",
    "pending",
    "initializing",
    "resuming",
    "stopping",
    "snapshotting",
    "hibernating",
}
_PENDING_SNAPSHOTS = {"creating", "pending", "running", "snapshotting", "inprogress"}
_READY_SNAPSHOTS = {"completed", "ready", "success", "succeeded"}


def owner_session_key(tool_id: str, owner: str) -> str:
    return "studio-" + hashlib.sha256(f"{tool_id}\0{owner}".encode()).hexdigest()[:32]


class PersistentWorkspaceProjects:
    def __init__(
        self, gateway: Any, tool_id: str, *, recovery_timeout: float = 120
    ) -> None:
        self.recovery_timeout = recovery_timeout
        self.gateway = gateway
        self.tool_id = tool_id
        self.region = os.getenv("AGENTKIT_SANDBOX_REGION", "")
        self.locks: dict[str, asyncio.Lock] = {}

    def _lock(self, owner: str) -> asyncio.Lock:
        if owner not in self.locks and len(self.locks) >= 128:
            raise HTTPException(429, "工作区正在处理较多请求，请稍后重试")
        return self.locks.setdefault(owner, asyncio.Lock())

    def _check_owner(self, session: SandboxCloudSession, owner: str) -> None:
        if (
            session.user_session_id != owner_session_key(self.tool_id, owner)
            or session.created_by not in {"", owner}
            or session.agent_kind not in {"", _KIND}
        ):
            raise HTTPException(404, "工作区不存在")

    async def _resolve(
        self, owner: str, creator: str, *, create_if_missing: bool = True
    ) -> SandboxCloudSession:
        """Caller holds the owner lock; snapshots retain the stable user-session ID."""
        key = owner_session_key(self.tool_id, owner)
        deadline = asyncio.get_running_loop().time() + self.recovery_timeout
        while True:
            sessions = [
                s
                for s in await self.gateway.list_sessions(self.tool_id)
                if s.user_session_id == key
            ]
            for session in sessions:
                self._check_owner(session, owner)
            ready = [
                s
                for s in sessions
                if not _expired(s) and s.status.lower() == "ready" and s.endpoint
            ]
            if len(ready) > 1:
                raise HTTPException(409, "检测到多个个人工作区会话，请联系管理员处理")
            if ready:
                return ready[0]
            snapshots = [
                s
                for s in await self.gateway.list_snapshots(self.tool_id)
                if s.user_session_id == key
            ]
            for snapshot in snapshots:
                if snapshot.created_by not in {"", owner}:
                    raise HTTPException(404, "工作区不存在")
            latest = max(snapshots, key=lambda s: s.created_at) if snapshots else None
            transitioning = any(
                s.status.lower() in _TRANSITIONAL_SESSIONS for s in sessions
            )
            if (
                not transitioning
                and latest
                and latest.status.lower() in _READY_SNAPSHOTS
            ):
                session = await self.gateway.resume_snapshot(latest)
                self._check_owner(session, owner)
                if (
                    session.status.lower() == "ready"
                    and session.endpoint
                    and not _expired(session)
                ):
                    return session
                # Another request may already be resuming this same session.
                transitioning = True
            pending_snapshot = latest and latest.status.lower() in _PENDING_SNAPSHOTS
            awaiting_snapshot = (
                bool(sessions)
                and not latest
                and all(
                    s.status.lower()
                    in {"expired", "deleted", "stopped", "sleeping", "hibernated"}
                    for s in sessions
                )
            )
            missing_existing = not create_if_missing and not snapshots and not sessions
            if (
                transitioning
                or pending_snapshot
                or awaiting_snapshot
                or missing_existing
            ):
                if asyncio.get_running_loop().time() >= deadline:
                    raise HTTPException(504, "工作区恢复超时，项目仍保留，请重试")
                await asyncio.sleep(2)
                continue
            if snapshots or sessions:
                # Never replace a user's existing filesystem with an empty one.
                raise HTTPException(409, "工作区暂时无法恢复，原项目仍保留，请重试")
            break
        tool = await self.gateway.get_tool(self.tool_id)
        if not getattr(tool, "enable_snapshot", False):
            raise HTTPException(503, "当前 Sandbox 未启用持久化快照，请检查工作区配置")
        request = build_create_session_request(
            tool_id=self.tool_id,
            ttl_seconds=STUDIO_SANDBOX_TTL_SECONDS,
            user_session_id=key,
            display_name="Studio Workspace",
            username=owner,
            creator_name=creator,
            agent_kind=_KIND,
        )
        # The shared gateway handles SDK metadata compatibility and provider credentials.
        response = await self.gateway._call(
            "create_session", request, region=self.region
        )
        if not response.session_id:
            raise ValueError("Workspace creation returned no session ID")
        for _ in range(60):
            session = await self.gateway.get_session(self.tool_id, response.session_id)
            self._check_owner(session, owner)
            if session.status.lower() == "ready" and session.endpoint:
                return session
            if _expired(session):
                raise HTTPException(502, "个人工作区启动失败，请检查 Sandbox 状态")
            await asyncio.sleep(2)
        raise TimeoutError("Workspace startup timed out")

    async def state(self, owner: str) -> dict[str, str]:
        """Inspect the control plane without waking an idle workspace."""
        key = owner_session_key(self.tool_id, owner)
        sessions = [
            s
            for s in await self.gateway.list_sessions(self.tool_id)
            if s.user_session_id == key
        ]
        for session in sessions:
            self._check_owner(session, owner)
        ready = [
            s
            for s in sessions
            if s.status.lower() == "ready" and not _expired(s) and s.endpoint
        ]
        if len(ready) > 1:
            raise HTTPException(409, "检测到多个个人工作区会话，请联系管理员处理")
        if ready:
            return {
                "status": "ready",
                "sessionId": ready[0].instance_id,
                "expireAt": ready[0].expire_at,
            }
        return {"status": "sleeping", "sessionId": "", "expireAt": ""}

    @staticmethod
    async def _projects(session: SandboxCloudSession) -> list[str]:
        code = """import json,re
from pathlib import Path
root=Path('/home/gem/Projects')
names=sorted(p.name for p in root.iterdir() if p.is_dir() and not p.is_symlink() and (p/'.git').exists()
             and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}',p.name)) if root.exists() else []
print(json.dumps({'projects':names}))
"""
        result = await SandboxRemoteTransport(session.endpoint).exec_json(
            "python3 -c " + shlex.quote(code), timeout=20
        )
        names = result.get("projects")
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            raise ValueError("Invalid project directory response")
        for name in names:
            ProjectInput(name=name)
        return names

    @staticmethod
    async def describe(session: SandboxCloudSession, names: list[str]) -> list[dict]:
        code = """import json,os,subprocess
from pathlib import Path
from datetime import datetime,timezone
root=Path('/home/gem/Projects')
skip={'.git','.venv','venv','node_modules','__pycache__','.pytest_cache','.ruff_cache','.mypy_cache'}
items=[]
for name in NAMES:
    p=root/name
    if not p.is_dir() or p.is_symlink():
        continue
    files=directories=0
    for base,dirs,entries in os.walk(p,followlinks=False):
        dirs[:]=[d for d in dirs if d not in skip and not (Path(base)/d).is_symlink()]
        directories+=len(dirs)
        files+=sum(1 for f in entries if (Path(base)/f).is_file() and not (Path(base)/f).is_symlink())
    marker=p/'.git'/'studio-created-at'
    created=None
    try:
        created=float(marker.read_text())
    except (OSError,ValueError):
        created=getattr(p.stat(),'st_birthtime',None)
        if not created:
            result=subprocess.run(['stat','-c','%W',str(p)],capture_output=True,text=True,timeout=2)
            if result.returncode == 0 and result.stdout.strip().isdigit():
                created=int(result.stdout.strip()) or None
    items.append({'name':name,'fileCount':files,'directoryCount':directories,
                  'createdAt':datetime.fromtimestamp(created,timezone.utc).isoformat() if created else None})
print(json.dumps({'projects':items}))
""".replace("NAMES", repr(names))
        result = await SandboxRemoteTransport(session.endpoint).exec_json(
            "python3 -c " + shlex.quote(code), timeout=20
        )
        items = result.get("projects")
        if not isinstance(items, list) or any(
            not isinstance(item, dict)
            or item.get("name") not in names
            or type(item.get("fileCount")) is not int
            or type(item.get("directoryCount")) is not int
            for item in items
        ):
            raise ValueError("Invalid project metadata response")
        return items

    async def list(
        self, owner: str, creator: str
    ) -> tuple[SandboxCloudSession, list[str]]:
        async with self._lock(owner):
            session = await self._resolve(owner, creator)
            return session, await self._projects(session)

    async def create(self, owner: str, creator: str, name: str) -> SandboxCloudSession:
        ProjectInput(name=name)
        async with self._lock(owner):
            session = await self._resolve(owner, creator)
            if name in await self._projects(session):
                raise HTTPException(409, "项目名称已存在，请从项目列表打开")
            index = os.getenv(
                "STUDIO_WORKSPACE_DEPENDENCY_INDEX",
                "https://mirrors.aliyun.com/pypi/simple/",
            )
            from frontend.server.workspace_templates import default_project_template

            template_json = json.dumps(
                default_project_template(name), ensure_ascii=False
            )
            code = (
                "import os,subprocess,json,time; from pathlib import Path; "
                f"p=Path('/home/gem/Projects')/{name!r}; "
                "assert not p.exists() and not p.is_symlink(), 'Project already exists'; "
                f"cmd=['studio-project-create',{name!r},'--json','--template-stdin']; "
                "cmd=(['runuser','-u','gem','--']+cmd) if os.geteuid()==0 else cmd; "
                f"env=dict(os.environ,UV_DEFAULT_INDEX={index!r},UV_INDEX_URL={index!r}); "
                f"subprocess.run(cmd,input={template_json!r},text=True,check=True,capture_output=True,env=env); "
                "assert (p/'.git').exists() and (p/'.venv/bin/python').exists(); "
                "(p/'.git'/'studio-created-at').write_text(str(time.time())); "
                "print(json.dumps({'ready':True}))"
            )
            result = await SandboxRemoteTransport(session.endpoint).exec_json(
                "python3 -c " + shlex.quote(code), timeout=90
            )
            if result.get("ready") is not True:
                raise ValueError("Project initialization failed")
            return session

    async def _renew_if_needed(
        self, session: SandboxCloudSession
    ) -> SandboxCloudSession:
        if not session.expire_at:
            raise ValueError("Workspace session has no expiration time")
        expiry = datetime.fromisoformat(session.expire_at.replace("Z", "+00:00"))
        remaining = (
            expiry.replace(tzinfo=expiry.tzinfo or timezone.utc)
            - datetime.now(timezone.utc)
        ).total_seconds()
        if remaining >= 3600:
            return session
        response = await self.gateway._call(
            "set_session_ttl",
            SetSessionTtlRequest(
                ToolId=self.tool_id,
                SessionId=session.instance_id,
                Ttl=STUDIO_SANDBOX_TTL_SECONDS,
                TtlUnit="second",
            ),
            region=session.region or self.region,
        )
        if not response.expire_at:
            raise ValueError("Session renewal returned no expiration time")
        return replace(session, expire_at=response.expire_at)

    async def open(self, owner: str, creator: str, name: str) -> SandboxCloudSession:
        ProjectInput(name=name)
        async with self._lock(owner):
            session = await self._resolve(owner, creator, create_if_missing=False)
            if name not in await self._projects(session):
                raise HTTPException(404, "项目目录不存在")
            return await self._renew_if_needed(session)
