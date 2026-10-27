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


"""Session-scoped AgentKit lifecycle management, independent of MCP and VeADK.

This manager serializes a whole turn using a local POSIX file lock. It supports
multiple processes on one host, not distributed workers or detached remote jobs.
Only bindings created by this manager are eligible for lifecycle operations.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from agentkit.sdk.tools import types as api
from agentkit.sdk.tools.client import AgentkitToolsClient

try:
    import fcntl
except ImportError:  # Windows may still import the package.
    fcntl = None


class SandboxError(RuntimeError):
    """Safe lifecycle diagnostic: never contains credentials or signed URLs."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SessionKey:
    """Trusted app/user/chat identity, independent of the physical SessionId."""

    app_name: str
    user_id: str
    session_id: str


@dataclass(frozen=True)
class SandboxLease:
    """Ready physical Session and its transient, credential-bearing MCP URL."""

    session_id: str
    mcp_url: str = field(repr=False)


def _mcp_endpoint(endpoint: str) -> str:
    try:
        parts = urlsplit(endpoint)
    except ValueError:
        raise SandboxError("Invalid sandbox endpoint URL") from None
    if (
        parts.scheme not in {"http", "https"}
        or not parts.netloc
        or parts.username
        or parts.password
        or parts.fragment
        or parts.path.rstrip("/") not in {"", "/mcp"}
    ):
        raise SandboxError("Expected an HTTP(S) sandbox endpoint at / or /mcp")
    return urlunsplit(parts._replace(path="/mcp"))


def _api_error_code(error: BaseException) -> str | None:
    """Read structured OpenAPI errors, including the SDK's HTTP-error cause."""
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        code = getattr(error, "error_code", None)
        if isinstance(code, str) and code:
            return code
        for arg in error.args:
            if not isinstance(arg, (str, bytes)):
                continue
            try:
                payload = json.loads(arg)
                code = payload["ResponseMetadata"]["Error"]["Code"]
                if isinstance(code, str) and code:
                    return code
            except (ValueError, KeyError, TypeError):
                continue
        error = error.__cause__
    return None


class SandboxManager:
    """Own AgentKit Session bindings on a trusted local POSIX filesystem.

    Acquire holds exclusive use until its async context exits. Other lifecycle
    operations wait for that context, but cloud TTL and detached jobs remain the
    caller's responsibility. No operation adopts an externally supplied Session.
    """

    def __init__(
        self,
        *,
        tool_id: str,
        state_dir: Path | str,
        region: str = "cn-beijing",
        ttl: int = 1800,
        ready_timeout: float = 120.0,
        poll_interval: float = 1.0,
        client: Any = None,
    ) -> None:
        if fcntl is None:
            raise NotImplementedError("SandboxManager requires POSIX file locking")
        if not tool_id or not 60 <= ttl <= 86400:
            raise ValueError("tool_id is required; ttl must be between 60 and 86400")
        if ready_timeout <= 0 or poll_interval <= 0:
            raise ValueError("timeouts must be positive")
        self.tool_id, self.region, self.ttl = tool_id, region, ttl
        self.ready_timeout, self.poll_interval = ready_timeout, poll_interval
        self.client = (
            client if client is not None else AgentkitToolsClient(region=region)
        )
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _path(self, key):
        parts = [self.region, self.tool_id, key.app_name, key.user_id, key.session_id]
        digest = hashlib.sha256(json.dumps(parts).encode()).hexdigest()
        return self.state_dir / f"{digest}.json"

    @asynccontextmanager
    async def _locked(self, key):
        path = self._path(key)
        fd = os.open(path.with_suffix(".lock"), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            deadline = time.monotonic() + self.ready_timeout
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise SandboxError(
                            "Session is busy; lifecycle operation was not started"
                        )
                    await asyncio.sleep(self.poll_interval)
            yield path
        finally:
            os.close(fd)

    @staticmethod
    def _read(path):
        if not path.exists():
            return None
        value = json.loads(path.read_text())
        if not isinstance(value, dict) or value.get("version") != 1:
            raise SandboxError("Unsupported or corrupt sandbox binding")
        return value

    @staticmethod
    def _save(path, record):
        fd, name = tempfile.mkstemp(dir=path.parent, prefix=".binding-")
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(record, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    async def _call(self, method, request):
        # A cancelled await cannot stop a synchronous SDK HTTP request. Wait for
        # its thread before releasing the lifecycle lock; never replay the RPC.
        task = asyncio.create_task(
            asyncio.to_thread(getattr(self.client, method), request)
        )
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except Exception:  # noqa: BLE001 - preserve the original cancellation
                    break
            if task.done() and not task.cancelled():
                task.exception()
            raise
        except Exception as exc:  # noqa: BLE001 - sanitize all SDK/transport errors
            code = _api_error_code(exc)
            raise SandboxError(
                f"{method} failed ({type(exc).__name__}); reconcile remote state before retrying",
                code=code,
            ) from None

    async def _get(self, record):
        value = await self._call(
            "get_session",
            api.GetSessionRequest(
                tool_id=self.tool_id,
                session_id=record["session_id"],
            ),
        )
        self._check_id(value, record["session_id"])
        return value

    @staticmethod
    def _check_id(value, expected):
        if getattr(value, "session_id", None) not in {None, expected}:
            raise SandboxError("Control plane returned a different sandbox SessionId")

    @staticmethod
    def _status(value):
        return (getattr(value, "status", None) or "").lower()

    async def _wait(self, record, target):
        deadline = time.monotonic() + self.ready_timeout
        while True:
            value = await self._get(record)
            status = self._status(value)
            if status == target:
                return value
            if status in {"failed", "error", "terminated", "deleted"}:
                raise SandboxError(f"Sandbox entered terminal state {status}")
            if time.monotonic() >= deadline:
                raise SandboxError(
                    f"Timed out waiting for {target}; remote state may still change"
                )
            await asyncio.sleep(self.poll_interval)

    async def _recover_create(self, path, record):
        matches, seen, cursor = [], set(), None
        while True:
            page = await self._call(
                "list_sessions",
                api.ListSessionsRequest(
                    tool_id=self.tool_id,
                    max_results=100,
                    next_token=cursor,
                    filters=[
                        api.FiltersItemForListSessions(
                            name="UserSessionId",
                            values=[record["user_session_id"]],
                        )
                    ],
                ),
            )
            matches.extend(
                s
                for s in page.session_infos or []
                if s.user_session_id == record["user_session_id"]
            )
            cursor = page.next_token
            if not cursor:
                break
            if cursor in seen:
                raise SandboxError("Repeated ListSessions page token")
            seen.add(cursor)
        if len(matches) != 1 or not matches[0].session_id:
            raise SandboxError(
                "Create outcome is unconfirmed or ambiguous; binding retained, no new sandbox created"
            )
        record["session_id"] = matches[0].session_id
        self._save(path, record)

    async def _binding(self, path, *, create):
        record = self._read(path)
        if record is None:
            if not create:
                raise SandboxError("No managed sandbox binding exists")
            record = {
                "version": 1,
                "tool_id": self.tool_id,
                "phase": "creating",
                "user_session_id": f"veadk_mcp_{uuid.uuid4().hex}",
            }
            # Save intent BEFORE the remote create. A restart recovers this same
            # unique UserSessionId and must not silently create another sandbox.
            self._save(path, record)
            try:
                value = await self._call(
                    "create_session",
                    api.CreateSessionRequest(
                        tool_id=self.tool_id,
                        user_session_id=record["user_session_id"],
                        ttl=self.ttl,
                    ),
                )
                if not value.session_id:
                    raise SandboxError("CreateSession returned no SessionId")
                record["session_id"] = value.session_id
                self._save(path, record)
            except SandboxError:
                await self._recover_create(path, record)
        if record.get("tool_id") != self.tool_id:
            raise SandboxError("Binding belongs to a different Tool")
        if not record.get("session_id"):
            await self._recover_create(path, record)
        return record

    async def _ready(self, path, record):
        if record["phase"] in {"deleting", "deleted"}:
            raise SandboxError(
                "Sandbox was deleted or is deleting; use a new session key"
            )
        value = await self._get(record)
        status = self._status(value)
        if status == "pausing" or record["phase"] == "pausing":
            value = await self._wait(record, "paused")
            status = "paused"
        if status == "paused":
            record["phase"] = "resuming"
            self._save(path, record)
            response = await self._call(
                "resume_session",
                api.ResumeSessionRequest(
                    tool_id=self.tool_id,
                    session_id=record["session_id"],
                    ttl=self.ttl,
                ),
            )
            self._check_id(response, record["session_id"])
        elif status not in {"ready", "starting", "resuming"}:
            raise SandboxError(
                f"Sandbox is not reusable ({status}); replacement is not automatic"
            )
        value = await self._wait(record, "ready")
        endpoint = getattr(value, "endpoint", None)
        if not endpoint:
            raise SandboxError("Ready sandbox has no Endpoint")
        lease = SandboxLease(record["session_id"], _mcp_endpoint(endpoint))
        record["phase"] = "ready"
        self._save(path, record)
        return lease

    @asynccontextmanager
    async def acquire(self, key: SessionKey) -> AsyncIterator[SandboxLease]:
        """Create/resume and hold exclusive use for one complete synchronous turn."""
        async with self._locked(key) as path:
            record = await self._binding(path, create=True)
            lease = await self._ready(path, record)
            try:
                yield lease
            finally:
                record["last_used_at"] = time.time()
                self._save(path, record)

    async def resume(self, key: SessionKey) -> SandboxLease:
        """Explicitly resume an existing binding; does not create one."""
        async with self._locked(key) as path:
            return await self._ready(path, await self._binding(path, create=False))

    async def pause(self, key: SessionKey) -> None:
        """Wait for active use to finish, request pause, and confirm Paused."""
        async with self._locked(key) as path:
            record = await self._binding(path, create=False)
            if record["phase"] in {"deleted", "deleting"}:
                raise SandboxError("Cannot pause a deleted/deleting sandbox")
            value = await self._get(record)
            status = self._status(value)
            if status in {"starting", "resuming"}:
                value = await self._wait(record, "ready")
                status = self._status(value)
            if status == "ready":
                record["phase"] = "pausing"
                self._save(path, record)
                response = await self._call(
                    "pause_session",
                    api.PauseSessionRequest(
                        tool_id=self.tool_id,
                        session_id=record["session_id"],
                    ),
                )
                self._check_id(response, record["session_id"])
            elif status not in {"paused", "pausing"}:
                raise SandboxError(f"Cannot pause sandbox in state {status}")
            await self._wait(record, "paused")
            record["phase"] = "paused"
            self._save(path, record)

    async def delete(self, key: SessionKey) -> None:
        """Delete only this managed binding, retaining a tombstone after confirmation."""
        async with self._locked(key) as path:
            record = await self._binding(path, create=False)
            if record["phase"] == "deleted":
                return
            record["phase"] = "deleting"
            self._save(path, record)
            try:
                response = await self._call(
                    "delete_session",
                    api.DeleteSessionRequest(
                        tool_id=self.tool_id,
                        session_id=record["session_id"],
                    ),
                )
                self._check_id(response, record["session_id"])
            except SandboxError as exc:
                if not self._is_not_found(exc):
                    raise
            deadline = time.monotonic() + self.ready_timeout
            while True:
                try:
                    value = await self._get(record)
                    if self._status(value) in {"deleted", "terminated"}:
                        break
                except SandboxError as exc:
                    if self._is_not_found(exc):
                        break
                    raise
                if time.monotonic() >= deadline:
                    raise SandboxError(
                        "Deletion is not confirmed; binding remains deleting"
                    )
                await asyncio.sleep(self.poll_interval)
            record["phase"] = "deleted"
            self._save(path, record)

    @staticmethod
    def _is_not_found(exc):
        return exc.code in {
            "InvalidSession.NotFound",
            "InvalidResource.NotFound",
            "SessionNotFound",
        }

    async def status(self, key: SessionKey) -> dict[str, str]:
        """Return binding phase and remote state without endpoint credentials."""
        async with self._locked(key) as path:
            record = await self._binding(path, create=False)
            result = {"session_id": record["session_id"], "phase": record["phase"]}
            if record["phase"] != "deleted":
                result["remote_status"] = self._status(await self._get(record))
            return result
