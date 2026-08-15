# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""AgentKit Session, Exec, and File adapter used by Studio migration."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import requests
from agentkit.sdk.tools import types as tools_types
from agentkit.toolkit.cli.sandbox.sandbox_client import (
    SANDBOX_FILE_DOWNLOAD_ROUTE,
    build_bash_exec_url,
    build_file_url,
)

from veadk.cli.agentkit_sandbox_region import (
    is_agentkit_resource_not_found,
    sandbox_region_candidates,
)
from veadk.cli.agentkit_session_metadata import (
    build_create_session_request,
    build_list_sessions_request,
    call_session_client,
    session_username,
)
from veadk.cli.frontend_skill_creator import _sandbox_model_config
from veadk.utils.cloud_provider import cloud_provider_from_env

_TOOL_ID_ENV = "SANDBOX_DEV"
_DEVENV_IMAGE_ENV = "VEADK_DEVENV_IMAGE"
_EXPECTED_TOOL_TYPE = "DevEnv"
_TASK_ID_PREFIX = "migration-v1-"
_READ_TIMEOUT = (10, 120)
_WRITE_TIMEOUT = (10, 120)
_BASH_OUTPUT_ROUTE = "/v1/bash/output"
_RETRYABLE_HTTP_STATUSES = {408, 429, 500, 502, 503, 504}
_SESSION_READY_ATTEMPTS = 31
_SESSION_READY_INTERVAL_SECONDS = 2
ANALYSIS_START_MARKER = "VEADK_MIGRATION_ANALYSIS_STARTED_V1"
MIGRATION_START_MARKER = "VEADK_MIGRATION_EXECUTION_STARTED_V1"
_BACKGROUND_START_MARKERS = {
    "start_analysis": ANALYSIS_START_MARKER,
    "start_migration": MIGRATION_START_MARKER,
}
_RELEASED_SESSION_STATUSES = {
    "createfailed",
    "deleted",
    "deleting",
    "error",
    "expired",
    "failed",
}

logger = logging.getLogger(__name__)


class MigrationGatewayError(RuntimeError):
    """A remote dependency failure with explicit retry semantics."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 502,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable


class MigrationRemoteFileNotFound(MigrationGatewayError):
    def __init__(self, path: str) -> None:
        super().__init__(
            "MIGRATION_REMOTE_FILE_NOT_FOUND",
            f"远端迁移文件不存在：{path}",
            status_code=404,
        )


@dataclass(frozen=True)
class MigrationSandboxSession:
    tool_id: str
    session_id: str
    task_id: str
    endpoint: str
    region: str
    status: str
    created_at: str
    expire_at: str
    owner_id: str

    @property
    def released(self) -> bool:
        return self.status.strip().lower() in _RELEASED_SESSION_STATUSES


class MigrationGateway(Protocol):
    def capabilities(self) -> dict[str, object]: ...

    def create_session(
        self,
        *,
        task_id: str,
        owner_id: str,
        creator_name: str,
        display_name: str,
        ttl_seconds: int,
    ) -> MigrationSandboxSession: ...

    def list_sessions(self, owner_id: str) -> list[MigrationSandboxSession]: ...

    def find_session(
        self,
        task_id: str,
        owner_id: str,
    ) -> MigrationSandboxSession: ...

    def put_file(
        self,
        session: MigrationSandboxSession,
        path: str,
        content: bytes,
        *,
        media_type: str,
    ) -> None: ...

    def get_file(
        self,
        session: MigrationSandboxSession,
        path: str,
        *,
        max_bytes: int,
    ) -> bytes: ...

    def execute_bash(
        self,
        session: MigrationSandboxSession,
        command: str,
        *,
        operation: str,
        timeout_seconds: int,
    ) -> dict[str, object]: ...

    def delete_session(self, session: MigrationSandboxSession) -> None: ...


def _tool_model_capability(tool: Any) -> dict[str, object]:
    envs = {
        str(getattr(item, "key", "") or ""): str(
            getattr(item, "value", "") or ""
        ).strip()
        for item in (getattr(tool, "envs", None) or [])
        if getattr(item, "key", None)
    }
    _, expected_base_url = _sandbox_model_config(cloud_provider_from_env())
    return {
        "configured": bool(
            envs.get("CODEX_MODEL")
            and envs.get("CODEX_API_KEY")
            and envs.get("CODEX_BASE_URL", "").rstrip("/")
            == expected_base_url.rstrip("/")
        ),
        "id": envs.get("CODEX_MODEL", ""),
    }


class MigrationSandboxGateway:
    """Stateless adapter for one-hour Dev Sandbox migration Sessions."""

    def __init__(
        self,
        *,
        tool_id: str | None = None,
        region: str | None = None,
        tools_client_factory: Callable[[str], Any],
    ) -> None:
        self._tool_id = (tool_id or os.getenv(_TOOL_ID_ENV) or "").strip()
        self._regions = sandbox_region_candidates(
            region or os.getenv("AGENTKIT_SANDBOX_REGION"),
            provider=cloud_provider_from_env(),
        )
        self._tools_client_factory = tools_client_factory

    def _client(self, region: str) -> Any:
        return self._tools_client_factory(region)

    def _get_tool(self) -> tuple[Any, str]:
        if not self._tool_id:
            raise MigrationGatewayError(
                "MIGRATION_DEVENV_NOT_CONFIGURED",
                "管理员未配置 Dev Sandbox。",
                status_code=503,
            )
        request = tools_types.GetToolRequest(ToolId=self._tool_id)
        for index, region in enumerate(self._regions):
            try:
                return self._client(region).get_tool(request), region
            except Exception as error:
                if is_agentkit_resource_not_found(error) and index + 1 < len(
                    self._regions
                ):
                    continue
                raise MigrationGatewayError(
                    "MIGRATION_DEVENV_UNAVAILABLE",
                    "Dev Sandbox 暂不可用，请联系管理员检查配置。",
                    status_code=503,
                ) from error
        raise MigrationGatewayError(
            "MIGRATION_DEVENV_UNAVAILABLE",
            "Dev Sandbox 暂不可用，请联系管理员检查配置。",
            status_code=503,
        )

    def capabilities(self) -> dict[str, object]:
        provider = cloud_provider_from_env()
        if not self._tool_id:
            return {
                "enabled": False,
                "reason": "管理员未配置 Dev Sandbox。",
                "provider": provider,
                "model": {"configured": False, "id": ""},
            }
        try:
            tool, _ = self._get_tool()
        except MigrationGatewayError:
            return {
                "enabled": False,
                "reason": "Dev Sandbox 暂不可用，请联系管理员检查配置。",
                "provider": provider,
                "model": {"configured": False, "id": ""},
            }
        model = _tool_model_capability(tool)
        expected_image = (os.getenv(_DEVENV_IMAGE_ENV) or "").strip()
        valid_tool = (
            str(getattr(tool, "tool_type", "") or "") == _EXPECTED_TOOL_TYPE
            and str(getattr(tool, "status", "") or "") == "Ready"
        )
        if expected_image:
            valid_tool = valid_tool and (
                str(getattr(tool, "image_url", "") or "") == expected_image
            )
        if not valid_tool:
            return {
                "enabled": False,
                "reason": "Dev Sandbox 暂不可用，请联系管理员检查配置。",
                "provider": provider,
                "model": model,
            }
        if not model["configured"]:
            return {
                "enabled": False,
                "reason": "Dev Sandbox 模型配置不可用，请重新部署 Studio。",
                "provider": provider,
                "model": model,
            }
        return {
            "enabled": True,
            "reason": "",
            "provider": provider,
            "model": model,
        }

    @staticmethod
    def _session(
        value: Any,
        *,
        tool_id: str,
        region: str,
        owner_id: str = "",
        task_id: str = "",
    ) -> MigrationSandboxSession:
        session_id = str(getattr(value, "session_id", "") or "").strip()
        if not session_id:
            raise MigrationGatewayError(
                "MIGRATION_SESSION_RESPONSE_INVALID",
                "Dev Sandbox 创建结果缺少 Session ID。",
            )
        return MigrationSandboxSession(
            tool_id=tool_id,
            session_id=session_id,
            task_id=str(getattr(value, "user_session_id", "") or task_id).strip(),
            endpoint=str(getattr(value, "endpoint", "") or "").strip(),
            region=region,
            status=str(getattr(value, "status", "") or "Unknown").strip(),
            created_at=str(getattr(value, "created_at", "") or "").strip(),
            expire_at=str(getattr(value, "expire_at", "") or "").strip(),
            owner_id=session_username(value) or owner_id,
        )

    def _list_region(
        self,
        region: str,
        *,
        owner_id: str | None,
        task_id: str | None = None,
    ) -> list[MigrationSandboxSession]:
        next_token: str | None = None
        seen_tokens: set[str] = set()
        sessions: dict[str, MigrationSandboxSession] = {}
        client = self._client(region)
        for _ in range(100):
            if task_id is None:
                request = build_list_sessions_request(
                    tool_id=self._tool_id,
                    max_results=100,
                    next_token=next_token,
                    username=owner_id,
                )
            else:
                request = tools_types.ListSessionsRequest(
                    ToolId=self._tool_id,
                    MaxResults=100,
                    NextToken=next_token,
                    Filters=[
                        tools_types.FiltersItemForListSessions(
                            Name="UserSessionId",
                            Values=[task_id],
                        )
                    ],
                )
            response = call_session_client(client, "list_sessions", request)
            for value in response.session_infos or []:
                session = self._session(
                    value,
                    tool_id=self._tool_id,
                    region=region,
                )
                if not session.task_id.startswith(_TASK_ID_PREFIX):
                    continue
                if task_id is not None and session.task_id != task_id:
                    continue
                if owner_id is not None and session.owner_id != owner_id:
                    continue
                sessions[session.session_id] = session
            next_token = str(getattr(response, "next_token", "") or "").strip() or None
            if next_token is None:
                return sorted(
                    sessions.values(),
                    key=lambda item: item.created_at,
                    reverse=True,
                )
            if next_token in seen_tokens:
                raise MigrationGatewayError(
                    "MIGRATION_SESSION_LIST_INVALID",
                    "Dev Sandbox 会话分页响应异常。",
                )
            seen_tokens.add(next_token)
        raise MigrationGatewayError(
            "MIGRATION_SESSION_LIST_INVALID",
            "Dev Sandbox 会话分页超过安全上限。",
        )

    def list_sessions(self, owner_id: str) -> list[MigrationSandboxSession]:
        if not self._tool_id:
            return []
        for index, region in enumerate(self._regions):
            try:
                return self._list_region(region, owner_id=owner_id)
            except Exception as error:
                if is_agentkit_resource_not_found(error) and index + 1 < len(
                    self._regions
                ):
                    continue
                if isinstance(error, MigrationGatewayError):
                    raise
                raise MigrationGatewayError(
                    "MIGRATION_SESSION_LIST_FAILED",
                    "暂时无法读取迁移会话。",
                    retryable=isinstance(
                        error,
                        (requests.ConnectionError, requests.Timeout),
                    ),
                ) from error
        return []

    def find_session(
        self,
        task_id: str,
        owner_id: str,
    ) -> MigrationSandboxSession:
        if not self._tool_id:
            raise MigrationGatewayError(
                "MIGRATION_DEVENV_NOT_CONFIGURED",
                "管理员未配置 Dev Sandbox。",
                status_code=503,
            )
        for index, region in enumerate(self._regions):
            try:
                matches = self._list_region(
                    region,
                    owner_id=owner_id,
                    task_id=task_id,
                )
            except Exception as error:
                if is_agentkit_resource_not_found(error) and index + 1 < len(
                    self._regions
                ):
                    continue
                if isinstance(error, MigrationGatewayError):
                    raise
                raise MigrationGatewayError(
                    "MIGRATION_SESSION_READ_FAILED",
                    "暂时无法读取迁移会话。",
                    retryable=isinstance(
                        error,
                        (requests.ConnectionError, requests.Timeout),
                    ),
                ) from error
            if not matches:
                continue
            if len(matches) != 1:
                raise MigrationGatewayError(
                    "MIGRATION_SESSION_AMBIGUOUS",
                    "迁移会话状态异常，请联系管理员检查。",
                )
            return matches[0]
        raise MigrationGatewayError(
            "MIGRATION_TASK_NOT_FOUND",
            "迁移会话不存在或已过期。",
            status_code=404,
        )

    def _wait_for_ready_session(
        self,
        region: str,
        *,
        task_id: str,
        owner_id: str,
        initial: MigrationSandboxSession | None = None,
    ) -> MigrationSandboxSession | None:
        current = initial
        for attempt in range(_SESSION_READY_ATTEMPTS):
            if current is not None:
                status = current.status.strip().lower()
                if current.endpoint and status in {"ready", "running"}:
                    return current
                if current.released:
                    raise MigrationGatewayError(
                        "MIGRATION_SESSION_CREATE_FAILED",
                        "Dev Sandbox 创建后进入失败状态，请新建迁移。",
                        status_code=502,
                    )
            if attempt == _SESSION_READY_ATTEMPTS - 1:
                break
            if initial is None:
                matches = self._list_region(
                    region,
                    owner_id=owner_id,
                    task_id=task_id,
                )
                if len(matches) > 1:
                    raise MigrationGatewayError(
                        "MIGRATION_SESSION_AMBIGUOUS",
                        "迁移会话状态异常，请联系管理员检查。",
                    )
                current = matches[0] if matches else None
            else:
                response = call_session_client(
                    self._client(region),
                    "get_session",
                    tools_types.GetSessionRequest(
                        ToolId=self._tool_id,
                        SessionId=initial.session_id,
                    ),
                )
                current = self._session(
                    response,
                    tool_id=self._tool_id,
                    region=region,
                    owner_id=owner_id,
                    task_id=task_id,
                )
            if current is None or not (
                current.endpoint
                and current.status.strip().lower() in {"ready", "running"}
            ):
                time.sleep(_SESSION_READY_INTERVAL_SECONDS)
        return None

    def create_session(
        self,
        *,
        task_id: str,
        owner_id: str,
        creator_name: str,
        display_name: str,
        ttl_seconds: int,
    ) -> MigrationSandboxSession:
        _, region = self._get_tool()
        existing = self._list_region(
            region,
            owner_id=owner_id,
            task_id=task_id,
        )
        if len(existing) > 1:
            raise MigrationGatewayError(
                "MIGRATION_SESSION_AMBIGUOUS",
                "迁移会话状态异常，请联系管理员检查。",
            )
        if existing:
            ready = self._wait_for_ready_session(
                region,
                task_id=task_id,
                owner_id=owner_id,
                initial=existing[0],
            )
            if ready is None:
                raise MigrationGatewayError(
                    "MIGRATION_SESSION_CREATE_INCOMPLETE",
                    "Dev Sandbox 未在时限内就绪，请刷新迁移列表确认。",
                )
            return ready
        request = build_create_session_request(
            tool_id=self._tool_id,
            ttl_seconds=ttl_seconds,
            user_session_id=task_id,
            display_name=display_name,
            username=owner_id,
            creator_name=creator_name,
        )
        try:
            response = self._client(region).create_session(request)
        except Exception as error:
            try:
                recovered = self._wait_for_ready_session(
                    region,
                    task_id=task_id,
                    owner_id=owner_id,
                )
            except Exception as recovery_error:  # noqa: BLE001
                logger.warning(
                    "Migration Session recovery query failed task_id=%s error_type=%s",
                    task_id,
                    type(recovery_error).__name__,
                )
                recovered = None
            if recovered is not None:
                return recovered
            raise MigrationGatewayError(
                "MIGRATION_SESSION_CREATE_UNCERTAIN",
                "Dev Sandbox 创建结果无法确认，请刷新迁移列表后再操作。",
                status_code=502,
                retryable=False,
            ) from error
        session = self._session(
            response,
            tool_id=self._tool_id,
            region=region,
            owner_id=owner_id,
            task_id=task_id,
        )
        if session.endpoint and session.status.strip().lower() in {"ready", "running"}:
            return session
        ready = self._wait_for_ready_session(
            region,
            task_id=task_id,
            owner_id=owner_id,
            initial=session,
        )
        if ready is None:
            raise MigrationGatewayError(
                "MIGRATION_SESSION_CREATE_INCOMPLETE",
                "Dev Sandbox 未在时限内就绪，请刷新迁移列表确认。",
            )
        return ready

    @staticmethod
    def _require_endpoint(session: MigrationSandboxSession) -> str:
        if session.released or not session.endpoint:
            raise MigrationGatewayError(
                "MIGRATION_SESSION_EXPIRED",
                "Dev Sandbox 已清理，无法继续操作。",
                status_code=410,
            )
        return session.endpoint

    def put_file(
        self,
        session: MigrationSandboxSession,
        path: str,
        content: bytes,
        *,
        media_type: str,
    ) -> None:
        endpoint = self._require_endpoint(session)
        try:
            response = requests.post(
                build_file_url(endpoint, "/v1/file/upload"),
                data={"path": path},
                files={"file": (path.rsplit("/", 1)[-1], content, media_type)},
                timeout=_WRITE_TIMEOUT,
            )
        except (requests.ConnectionError, requests.Timeout) as error:
            raise MigrationGatewayError(
                "MIGRATION_REMOTE_WRITE_UNCERTAIN",
                "写入 Dev Sandbox 的结果无法确认，请刷新迁移状态。",
                retryable=False,
            ) from error
        if response.status_code >= 400:
            raise MigrationGatewayError(
                "MIGRATION_REMOTE_WRITE_FAILED",
                "写入 Dev Sandbox 失败。",
                status_code=502,
                retryable=False,
            )

    def get_file(
        self,
        session: MigrationSandboxSession,
        path: str,
        *,
        max_bytes: int,
    ) -> bytes:
        endpoint = self._require_endpoint(session)
        try:
            response = requests.get(
                build_file_url(endpoint, SANDBOX_FILE_DOWNLOAD_ROUTE),
                params={"path": path, "change_policy": "abort"},
                timeout=_READ_TIMEOUT,
                stream=True,
            )
        except (requests.ConnectionError, requests.Timeout) as error:
            raise MigrationGatewayError(
                "MIGRATION_REMOTE_READ_FAILED",
                "读取 Dev Sandbox 失败，请稍后重试。",
                retryable=True,
            ) from error
        if response.status_code == 404:
            response.close()
            raise MigrationRemoteFileNotFound(path)
        if response.status_code >= 400:
            retryable = response.status_code in _RETRYABLE_HTTP_STATUSES
            response.close()
            raise MigrationGatewayError(
                "MIGRATION_REMOTE_READ_FAILED",
                "读取 Dev Sandbox 失败，请稍后重试。",
                retryable=retryable,
            )
        declared = response.headers.get("content-length")
        if declared:
            try:
                if int(declared) > max_bytes:
                    response.close()
                    raise MigrationGatewayError(
                        "MIGRATION_REMOTE_FILE_TOO_LARGE",
                        "远端迁移文件超过读取上限。",
                    )
            except ValueError:
                pass
        content = bytearray()
        try:
            for chunk in response.iter_content(1024 * 1024):
                if not chunk:
                    continue
                if len(content) + len(chunk) > max_bytes:
                    raise MigrationGatewayError(
                        "MIGRATION_REMOTE_FILE_TOO_LARGE",
                        "远端迁移文件超过读取上限。",
                    )
                content.extend(chunk)
        finally:
            response.close()
        return bytes(content)

    def execute_bash(
        self,
        session: MigrationSandboxSession,
        command: str,
        *,
        operation: str,
        timeout_seconds: int,
    ) -> dict[str, object]:
        endpoint = self._require_endpoint(session)
        deadline = time.monotonic() + timeout_seconds + 30
        start_marker = _BACKGROUND_START_MARKERS.get(operation, "")

        def response_data(response: requests.Response) -> dict[str, object]:
            if response.status_code >= 400:
                raise MigrationGatewayError(
                    "MIGRATION_REMOTE_EXEC_FAILED",
                    "Dev Sandbox 操作失败。",
                    retryable=False,
                )
            try:
                payload = response.json()
            except ValueError as error:
                raise MigrationGatewayError(
                    "MIGRATION_REMOTE_EXEC_INVALID",
                    "Dev Sandbox 返回了无效响应。",
                ) from error
            data = payload.get("data", payload) if isinstance(payload, dict) else {}
            if not isinstance(data, dict):
                raise MigrationGatewayError(
                    "MIGRATION_REMOTE_EXEC_INVALID",
                    "Dev Sandbox 返回了无效响应。",
                )
            return {str(key): value for key, value in data.items()}

        def command_state(data: dict[str, object]) -> tuple[str, object]:
            command = data.get("command")
            command_data = command if isinstance(command, dict) else {}
            status = str(command_data.get("status") or data.get("status") or "").lower()
            exit_code = command_data.get(
                "exit_code",
                data.get("exit_code", data.get("exitCode")),
            )
            return status, exit_code

        def background_launch_confirmed(
            data: dict[str, object],
            status: str,
        ) -> bool:
            if status != "running" or not start_marker:
                return False
            output = f"{data.get('stdout') or ''}\n{data.get('stderr') or ''}"
            return start_marker in output

        try:
            response = requests.post(
                build_bash_exec_url(endpoint),
                json={
                    "timeout": 1 if start_marker else min(timeout_seconds, 30),
                    "hard_timeout": timeout_seconds,
                    "command": command,
                },
                timeout=(10, min(timeout_seconds + 30, 180)),
            )
        except (requests.ConnectionError, requests.Timeout) as error:
            raise MigrationGatewayError(
                "MIGRATION_REMOTE_EXEC_UNCERTAIN",
                "Dev Sandbox 操作结果无法确认，请刷新迁移状态。",
                retryable=False,
            ) from error
        data = response_data(response)
        status, exit_code = command_state(data)
        session_id = str(data.get("session_id") or "").strip()
        command_id = str(data.get("command_id") or "").strip()
        offset = data.get("offset", 0)
        stderr_offset = data.get("stderr_offset", 0)

        while status == "running":
            if background_launch_confirmed(data, status):
                data["status"] = "accepted"
                data["exit_code"] = 0
                return data
            if (
                not session_id
                or not command_id
                or isinstance(offset, bool)
                or not isinstance(offset, int)
                or offset < 0
                or isinstance(stderr_offset, bool)
                or not isinstance(stderr_offset, int)
                or stderr_offset < 0
            ):
                raise MigrationGatewayError(
                    "MIGRATION_REMOTE_EXEC_INVALID",
                    "Dev Sandbox 返回了无效的命令轮询状态。",
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MigrationGatewayError(
                    "MIGRATION_REMOTE_EXEC_TIMEOUT",
                    "Dev Sandbox 操作超过执行时限。",
                    retryable=False,
                )
            wait_timeout = min(30, max(1, int(remaining)))
            try:
                response = requests.post(
                    build_file_url(endpoint, _BASH_OUTPUT_ROUTE),
                    json={
                        "session_id": session_id,
                        "command_id": command_id,
                        "offset": offset,
                        "stderr_offset": stderr_offset,
                        "wait": True,
                        "wait_timeout": wait_timeout,
                    },
                    timeout=(10, wait_timeout + 10),
                )
            except (requests.ConnectionError, requests.Timeout) as error:
                raise MigrationGatewayError(
                    "MIGRATION_REMOTE_EXEC_UNCERTAIN",
                    "Dev Sandbox 操作结果无法确认，请刷新迁移状态。",
                    retryable=False,
                ) from error
            data = response_data(response)
            status, exit_code = command_state(data)
            offset = data.get("offset", offset)
            stderr_offset = data.get("stderr_offset", stderr_offset)

        if status != "completed" or isinstance(exit_code, bool) or exit_code != 0:
            logger.warning(
                "Migration Sandbox command failed operation=%s status=%s exit_code=%s",
                operation,
                status or "missing",
                exit_code,
            )
            raise MigrationGatewayError(
                "MIGRATION_REMOTE_EXEC_FAILED",
                "Dev Sandbox 操作未成功完成。",
                retryable=False,
            )
        data["status"] = status
        data["exit_code"] = exit_code
        return data

    def delete_session(self, session: MigrationSandboxSession) -> None:
        try:
            self._client(session.region).delete_session(
                tools_types.DeleteSessionRequest(
                    ToolId=session.tool_id,
                    SessionId=session.session_id,
                )
            )
        except Exception as error:
            if is_agentkit_resource_not_found(error):
                return
            raise MigrationGatewayError(
                "MIGRATION_SESSION_DELETE_FAILED",
                "删除迁移会话失败，请刷新后重试。",
                retryable=False,
            ) from error


__all__ = [
    "ANALYSIS_START_MARKER",
    "MIGRATION_START_MARKER",
    "MigrationGateway",
    "MigrationGatewayError",
    "MigrationRemoteFileNotFound",
    "MigrationSandboxGateway",
    "MigrationSandboxSession",
]
