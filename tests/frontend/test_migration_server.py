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

from __future__ import annotations

import hashlib
import io
import json
import stat
import subprocess
import zipfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from frontend.server.migration.gateway import (
    MigrationGatewayError,
    MigrationRemoteFileNotFound,
    MigrationSandboxGateway,
    MigrationSandboxSession,
)
from frontend.server.migration.models import (
    ConfirmMigrationBody,
    CreateMigrationTaskBody,
)
from frontend.server.migration.routes import mount_migration_routes
from frontend.server.migration.service import (
    MIGRATION_ROOT,
    MIGRATION_SESSION_TTL_SECONDS,
    MIGRATION_UPLOAD_MAX_BYTES,
    MigrationError,
    MigrationService,
    validate_source_archive,
)
from veadk.cli.frontend_skill_creator import _sandbox_model_config


def source_zip(
    files: dict[str, bytes] | None = None,
    *,
    symlink: str | None = None,
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in (
            files
            or {
                "support_agent/agent.py": (
                    b"from langchain_core.runnables import RunnableLambda\n"
                    b"agent = RunnableLambda(lambda value: value)\n"
                ),
                "support_agent/requirements.txt": b"langchain-core\n",
            }
        ).items():
            archive.writestr(path, content)
        if symlink is not None:
            info = zipfile.ZipInfo(symlink)
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, b"agent.py")
    return output.getvalue()


def artifact_zip(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return output.getvalue()


class FakeMigrationGateway:
    def __init__(self) -> None:
        self.enabled = True
        self.sessions: dict[str, MigrationSandboxSession] = {}
        self.files: dict[tuple[str, str], bytes] = {}
        self.commands: list[tuple[str, str, str]] = []
        self.command_timeouts: list[tuple[str, int]] = []
        self.created: list[str] = []
        self.deleted: list[str] = []

    def capabilities(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "reason": "" if self.enabled else "Dev Sandbox 暂不可用",
        }

    def create_session(
        self,
        *,
        task_id: str,
        owner_id: str,
        creator_name: str,
        display_name: str,
        ttl_seconds: int,
    ) -> MigrationSandboxSession:
        assert creator_name == "Owner"
        assert display_name == "存量迁移"
        assert ttl_seconds == MIGRATION_SESSION_TTL_SECONDS
        self.created.append(task_id)
        existing = self.sessions.get(task_id)
        if existing is not None:
            return existing
        session = MigrationSandboxSession(
            tool_id="tool-dev",
            session_id=f"session-{task_id}",
            task_id=task_id,
            endpoint="https://sandbox.invalid",
            region="cn-beijing",
            status="Ready",
            created_at="2099-01-01T00:00:00Z",
            expire_at="2099-01-01T01:00:00Z",
            owner_id=owner_id,
        )
        self.sessions[task_id] = session
        return session

    def list_sessions(self, owner_id: str) -> list[MigrationSandboxSession]:
        return [
            session
            for session in self.sessions.values()
            if session.owner_id == owner_id
        ]

    def find_session(
        self,
        task_id: str,
        owner_id: str,
    ) -> MigrationSandboxSession:
        session = self.sessions.get(task_id)
        if session is None or session.owner_id != owner_id:
            raise MigrationError(
                "MIGRATION_TASK_NOT_FOUND",
                "迁移会话不存在或已过期。",
                status_code=404,
            )
        return session

    def put_file(
        self,
        session: MigrationSandboxSession,
        path: str,
        content: bytes,
        *,
        media_type: str,
    ) -> None:
        del media_type
        self.files[(session.task_id, path)] = content

    def get_file(
        self,
        session: MigrationSandboxSession,
        path: str,
        *,
        max_bytes: int,
    ) -> bytes:
        try:
            content = self.files[(session.task_id, path)]
        except KeyError as error:
            raise MigrationRemoteFileNotFound(path) from error
        if len(content) > max_bytes:
            raise MigrationError(
                "MIGRATION_REMOTE_FILE_TOO_LARGE",
                "远端迁移文件超过读取上限。",
                status_code=502,
            )
        return content

    def execute_bash(
        self,
        session: MigrationSandboxSession,
        command: str,
        *,
        operation: str,
        timeout_seconds: int,
    ) -> dict[str, object]:
        self.commands.append((session.task_id, operation, command))
        self.command_timeouts.append((operation, timeout_seconds))
        if operation == "accept_request":
            candidates = [
                content
                for (candidate_task_id, path), content in self.files.items()
                if candidate_task_id == session.task_id
                and "/state/.request-" in path
                and path.endswith(".json")
            ]
            assert len(candidates) == 1
            current = self.files.get(
                (session.task_id, f"{MIGRATION_ROOT}/request.json")
            )
            if current is not None:
                assert (
                    json.loads(current)["task_id"]
                    == json.loads(candidates[0])["task_id"]
                )
            else:
                self.files[(session.task_id, f"{MIGRATION_ROOT}/request.json")] = (
                    candidates[0]
                )
        elif operation == "prepare_source":
            candidates = [
                content
                for (candidate_task_id, path), content in self.files.items()
                if candidate_task_id == session.task_id
                and "/input/.source-" in path
                and path.endswith(".zip")
            ]
            assert len(candidates) == 1
            summary = validate_source_archive(candidates[0])
            self.files[(session.task_id, f"{MIGRATION_ROOT}/state/source.json")] = (
                json.dumps(
                    {
                        "schema_version": 1,
                        "sha256": hashlib.sha256(candidates[0]).hexdigest(),
                        "size": len(candidates[0]),
                        "file_count": summary.file_count,
                        "expanded_bytes": summary.expanded_bytes,
                    }
                ).encode()
            )
        elif operation == "start_analysis":
            self.files[
                (session.task_id, f"{MIGRATION_ROOT}/state/analysis-status.json")
            ] = json.dumps(
                {
                    "schema_version": 1,
                    "state": "analyzing",
                    "message": "正在分析项目",
                }
            ).encode()
        elif operation == "start_migration":
            confirmation_candidates = [
                (path, content)
                for (candidate_task_id, path), content in self.files.items()
                if candidate_task_id == session.task_id
                and "/state/.confirmation-" in path
            ]
            assert len(confirmation_candidates) == 1
            self.files[
                (session.task_id, f"{MIGRATION_ROOT}/state/confirmation.json")
            ] = confirmation_candidates[0][1]
            self.files[
                (session.task_id, f"{MIGRATION_ROOT}/delivery/migration-status.json")
            ] = json.dumps(
                {
                    "schema_version": 1,
                    "run_id": session.task_id,
                    "sequence": 1,
                    "state": "migrating",
                    "phase": "preparing",
                    "message": "正在迁移项目",
                    "artifact": {
                        "state": "none",
                        "preview_ready": False,
                        "download_ready": False,
                        "deploy_ready": False,
                    },
                    "updated_at": "2026-08-11T08:10:00Z",
                }
            ).encode()
        elif operation == "stop":
            self.files[(session.task_id, f"{MIGRATION_ROOT}/state/stopped.json")] = (
                json.dumps(
                    {
                        "schema_version": 1,
                        "state": "cancelled",
                        "message": "迁移已终止",
                    }
                ).encode()
            )
        return {"status": "finished", "exit_code": 0}

    def delete_session(self, session: MigrationSandboxSession) -> None:
        self.deleted.append(session.task_id)
        self.sessions.pop(session.task_id, None)


def analysis_result() -> dict[str, object]:
    return {
        "schema_version": 1,
        "summary": "这是一个 LangChain 客服 Agent。",
        "frameworks": [
            {
                "id": "langchain",
                "confidence": "high",
                "evidence": [
                    {
                        "path": "agent.py",
                        "line": 1,
                        "reason": "导入了 langchain_core",
                    }
                ],
            }
        ],
        "recommended": {
            "framework": "langchain",
            "entry": "agent.py:agent",
            "reason": "入口对象是 Runnable。",
        },
        "entries": [
            {
                "value": "agent.py:agent",
                "framework": "langchain",
                "evidence": "agent.py:2",
            }
        ],
        "boundary": {
            "include": ["Agent 编排与提示词"],
            "exclude": ["外部 CRM 凭证"],
        },
        "questions": [],
        "warnings": ["部署前需要配置模型凭证。"],
    }


def mark_analysis_ready(
    gateway: FakeMigrationGateway,
    task_id: str,
) -> None:
    gateway.files[(task_id, f"{MIGRATION_ROOT}/state/analysis-status.json")] = (
        json.dumps(
            {
                "schema_version": 1,
                "state": "ready",
                "message": "项目分析完成",
            }
        ).encode()
    )
    gateway.files[(task_id, f"{MIGRATION_ROOT}/state/analysis.json")] = json.dumps(
        analysis_result(), ensure_ascii=False
    ).encode()


def create_uploaded_task(
    service: MigrationService,
) -> tuple[str, dict[str, object]]:
    created = service.create_task(
        CreateMigrationTaskBody(
            sourceFileName="support-agent.zip",
            instruction="请保留客服流程，并使用中文输出迁移报告。",
        ),
        "owner-1",
        "Owner",
    )
    task_id = str(created["id"])
    uploaded = service.upload_source(
        task_id,
        "owner-1",
        source_zip(),
    )
    return task_id, uploaded


def test_migration_capability_and_session_contract_are_bounded() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)

    capability = service.capabilities()
    created = service.create_task(
        CreateMigrationTaskBody(
            sourceFileName="support-agent.zip",
            instruction="保留原有行为。",
        ),
        "owner-1",
        "Owner",
    )

    assert capability == {
        "enabled": True,
        "reason": "",
        "maxUploadBytes": 50 * 1024 * 1024,
        "sessionTtlSeconds": 3600,
        "frameworks": [
            "langchain",
            "langgraph",
            "adk",
            "strands",
            "agentcore",
            "dify",
            "any",
        ],
    }
    assert MIGRATION_UPLOAD_MAX_BYTES == 50 * 1024 * 1024
    assert created["state"] == "awaiting_upload"
    request = json.loads(
        gateway.files[(str(created["id"]), f"{MIGRATION_ROOT}/request.json")]
    )
    assert request["source_file_name"] == "support-agent.zip"
    assert request["instruction"] == "保留原有行为。"
    assert request["session_ttl_seconds"] == 3600
    assert "owner-1" not in json.dumps(request)


def test_create_task_is_idempotent_for_a_caller_owned_task_id() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id = "migration-v1-" + "a" * 32
    body = CreateMigrationTaskBody(
        taskId=task_id,
        sourceFileName="support-agent.zip",
        instruction="保留原有行为。",
    )

    first = service.create_task(body, "owner-1", "Owner")
    second = service.create_task(body, "owner-1", "Owner")

    assert first["id"] == task_id
    assert second["id"] == task_id
    assert gateway.created == [task_id, task_id]
    request = json.loads(gateway.files[(task_id, f"{MIGRATION_ROOT}/request.json")])
    assert request["task_id"] == task_id
    accept_command = gateway.commands[0][2]
    assert "fcntl.LOCK_EX" in accept_command
    assert "immutable_fields" in accept_command

    with pytest.raises(MigrationError) as conflict:
        service.create_task(
            CreateMigrationTaskBody(
                taskId=task_id,
                sourceFileName="different.zip",
            ),
            "owner-1",
            "Owner",
        )
    assert conflict.value.code == "MIGRATION_REQUEST_CONFLICT"
    assert conflict.value.status_code == 409
    assert task_id in gateway.sessions
    assert gateway.deleted == []


def test_service_rejects_a_malformed_request_state_file() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    created = service.create_task(
        CreateMigrationTaskBody(sourceFileName="support-agent.zip"),
        "owner-1",
        "Owner",
    )
    task_id = str(created["id"])
    path = (task_id, f"{MIGRATION_ROOT}/request.json")
    request = json.loads(gateway.files[path])
    request["unexpected"] = True
    gateway.files[path] = json.dumps(request).encode()

    with pytest.raises(MigrationError) as raised:
        service.get_task(task_id, "owner-1")

    assert raised.value.code == "MIGRATION_REQUEST_INVALID"
    assert raised.value.retryable is False


def test_service_rejects_a_malformed_source_state_file() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    created = service.create_task(
        CreateMigrationTaskBody(sourceFileName="support-agent.zip"),
        "owner-1",
        "Owner",
    )
    task_id = str(created["id"])
    gateway.files[(task_id, f"{MIGRATION_ROOT}/state/source.json")] = json.dumps(
        {
            "schema_version": 1,
            "sha256": "1" * 64,
            "size": True,
            "file_count": 1,
            "expanded_bytes": 10,
        }
    ).encode()

    with pytest.raises(MigrationError) as raised:
        service.get_task(task_id, "owner-1")

    assert raised.value.code == "MIGRATION_SOURCE_STATE_INVALID"
    assert raised.value.retryable is False


def test_service_rejects_a_malformed_analysis_status_file() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    gateway.files[(task_id, f"{MIGRATION_ROOT}/state/analysis-status.json")] = (
        json.dumps(
            {
                "schema_version": 1,
                "state": "analyzing",
                "message": ["not", "text"],
            }
        ).encode()
    )

    with pytest.raises(MigrationError) as raised:
        service.get_task(task_id, "owner-1")

    assert raised.value.code == "MIGRATION_ANALYSIS_STATE_INVALID"
    assert raised.value.retryable is False


def test_service_rejects_a_malformed_confirmation_state_file() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    mark_analysis_ready(gateway, task_id)
    service.confirm(
        task_id,
        "owner-1",
        ConfirmMigrationBody(
            framework="langchain",
            entry="agent.py:agent",
            appName="support-agent",
            answers={},
        ),
    )
    path = (task_id, f"{MIGRATION_ROOT}/state/confirmation.json")
    confirmation = json.loads(gateway.files[path])
    confirmation["answers"] = []
    gateway.files[path] = json.dumps(confirmation).encode()

    with pytest.raises(MigrationError) as raised:
        service.get_task(task_id, "owner-1")

    assert raised.value.code == "MIGRATION_CONFIRMATION_INVALID"
    assert raised.value.retryable is False


def test_service_rejects_a_malformed_process_exit_state_file() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    mark_analysis_ready(gateway, task_id)
    service.confirm(
        task_id,
        "owner-1",
        ConfirmMigrationBody(
            framework="langchain",
            entry="agent.py:agent",
            appName="support-agent",
            answers={},
        ),
    )
    gateway.files.pop((task_id, f"{MIGRATION_ROOT}/delivery/migration-status.json"))
    gateway.files[(task_id, f"{MIGRATION_ROOT}/state/migration-process-exit.json")] = (
        json.dumps({"schema_version": 1, "exit_code": 0, "unexpected": True}).encode()
    )

    with pytest.raises(MigrationError) as raised:
        service.get_task(task_id, "owner-1")

    assert raised.value.code == "MIGRATION_PROCESS_STATE_INVALID"
    assert raised.value.retryable is False


def test_service_rejects_a_malformed_stopped_state_file() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    gateway.files[(task_id, f"{MIGRATION_ROOT}/state/stopped.json")] = json.dumps(
        {
            "schema_version": 1,
            "state": "cancelled",
            "message": ["not", "text"],
        }
    ).encode()

    with pytest.raises(MigrationError) as raised:
        service.get_task(task_id, "owner-1")

    assert raised.value.code == "MIGRATION_STOP_STATE_INVALID"
    assert raised.value.retryable is False


@pytest.mark.parametrize(
    ("provider", "region"),
    [
        ("volcengine", "cn-beijing"),
        ("byteplus", "ap-southeast-1"),
    ],
)
def test_agentkit_gateway_creates_one_dev_session_without_snapshots(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    region: str,
) -> None:
    _, base_url = _sandbox_model_config(provider)

    class ToolsClient:
        def __init__(self) -> None:
            self.created: list[object] = []
            self.snapshot_calls = 0

        def get_tool(self, request: object) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                tool_type="DevEnv",
                status="Ready",
                image_url="",
                envs=[
                    SimpleNamespace(key="CODEX_MODEL", value="doubao-test"),
                    SimpleNamespace(key="CODEX_API_KEY", value="secret"),
                    SimpleNamespace(key="CODEX_BASE_URL", value=base_url),
                ],
            )

        def create_session(self, request: object) -> SimpleNamespace:
            self.created.append(request)
            return SimpleNamespace(
                session_id="session-1",
                user_session_id="migration-v1-" + "1" * 32,
                endpoint="https://sandbox.invalid",
                status="Ready",
                created_at="2026-08-11T08:00:00Z",
                expire_at="2026-08-11T09:00:00Z",
            )

        def list_sessions(self, request: object) -> SimpleNamespace:
            del request
            return SimpleNamespace(session_infos=[], next_token=None)

        def create_session_snapshot(self, request: object) -> None:
            del request
            self.snapshot_calls += 1

    client = ToolsClient()
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", provider)
    monkeypatch.setenv("CLOUD_PROVIDER", provider)
    gateway = MigrationSandboxGateway(
        tool_id="tool-dev",
        region=region,
        tools_client_factory=lambda region: client,
    )

    capability = gateway.capabilities()
    session = gateway.create_session(
        task_id="migration-v1-" + "1" * 32,
        owner_id="owner-1",
        creator_name="Owner",
        display_name="存量迁移",
        ttl_seconds=3600,
    )

    assert capability == {"enabled": True, "reason": ""}
    assert session.session_id == "session-1"
    assert len(client.created) == 1
    request = client.created[0]
    assert request.ttl == 3600
    assert request.ttl_unit == "second"
    assert request.user_session_id == "migration-v1-" + "1" * 32
    assert request.envs is None
    assert client.snapshot_calls == 0


def test_agentkit_gateway_waits_for_the_created_session_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, base_url = _sandbox_model_config("volcengine")

    class ToolsClient:
        def __init__(self) -> None:
            self.created = 0
            self.reads = 0

        def get_tool(self, request: object) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                tool_type="DevEnv",
                status="Ready",
                image_url="",
                envs=[
                    SimpleNamespace(key="CODEX_MODEL", value="doubao-test"),
                    SimpleNamespace(key="CODEX_API_KEY", value="secret"),
                    SimpleNamespace(key="CODEX_BASE_URL", value=base_url),
                ],
            )

        def create_session(self, request: object) -> SimpleNamespace:
            del request
            self.created += 1
            return SimpleNamespace(
                session_id="session-creating",
                user_session_id="migration-v1-" + "2" * 32,
                endpoint="",
                status="Creating",
                created_at="2026-08-11T08:00:00Z",
                expire_at="2026-08-11T09:00:00Z",
            )

        def list_sessions(self, request: object) -> SimpleNamespace:
            del request
            return SimpleNamespace(session_infos=[], next_token=None)

        def get_session(self, request: object) -> SimpleNamespace:
            del request
            self.reads += 1
            ready = self.reads >= 2
            return SimpleNamespace(
                session_id="session-creating",
                user_session_id="migration-v1-" + "2" * 32,
                endpoint="https://sandbox.invalid" if ready else "",
                status="Ready" if ready else "Creating",
                created_at="2026-08-11T08:00:00Z",
                expire_at="2026-08-11T09:00:00Z",
            )

    client = ToolsClient()
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "volcengine")
    monkeypatch.setenv("CLOUD_PROVIDER", "volcengine")
    monkeypatch.setattr("frontend.server.migration.gateway.time.sleep", lambda _: None)
    gateway = MigrationSandboxGateway(
        tool_id="tool-dev",
        region="cn-beijing",
        tools_client_factory=lambda region: client,
    )

    session = gateway.create_session(
        task_id="migration-v1-" + "2" * 32,
        owner_id="owner-1",
        creator_name="Owner",
        display_name="存量迁移",
        ttl_seconds=3600,
    )

    assert session.session_id == "session-creating"
    assert session.endpoint == "https://sandbox.invalid"
    assert session.status == "Ready"
    assert client.created == 1
    assert client.reads == 2


def test_agentkit_gateway_reconciles_ambiguous_create_without_recreating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, base_url = _sandbox_model_config("volcengine")

    class ToolsClient:
        def __init__(self) -> None:
            self.created = 0
            self.listed = 0

        def get_tool(self, request: object) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                tool_type="DevEnv",
                status="Ready",
                image_url="",
                envs=[
                    SimpleNamespace(key="CODEX_MODEL", value="doubao-test"),
                    SimpleNamespace(key="CODEX_API_KEY", value="secret"),
                    SimpleNamespace(key="CODEX_BASE_URL", value=base_url),
                ],
            )

        def create_session(self, request: object) -> SimpleNamespace:
            del request
            self.created += 1
            raise RuntimeError("connection closed after create")

        def list_sessions(self, request: object) -> SimpleNamespace:
            del request
            self.listed += 1
            if self.listed == 1:
                return SimpleNamespace(session_infos=[], next_token=None)
            ready = self.listed >= 3
            return SimpleNamespace(
                session_infos=[
                    SimpleNamespace(
                        session_id="session-reconciled",
                        user_session_id="migration-v1-" + "3" * 32,
                        endpoint="https://sandbox.invalid" if ready else "",
                        status="Ready" if ready else "Creating",
                        created_at="2026-08-11T08:00:00Z",
                        expire_at="2026-08-11T09:00:00Z",
                        metadata=[SimpleNamespace(key="Username", value="owner-1")],
                    )
                ],
                next_token=None,
            )

    client = ToolsClient()
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "volcengine")
    monkeypatch.setenv("CLOUD_PROVIDER", "volcengine")
    monkeypatch.setattr("frontend.server.migration.gateway.time.sleep", lambda _: None)
    gateway = MigrationSandboxGateway(
        tool_id="tool-dev",
        region="cn-beijing",
        tools_client_factory=lambda region: client,
    )

    session = gateway.create_session(
        task_id="migration-v1-" + "3" * 32,
        owner_id="owner-1",
        creator_name="Owner",
        display_name="存量迁移",
        ttl_seconds=3600,
    )

    assert session.session_id == "session-reconciled"
    assert session.endpoint == "https://sandbox.invalid"
    assert client.created == 1
    assert client.listed == 3


def test_agentkit_gateway_reuses_visible_session_before_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, base_url = _sandbox_model_config("volcengine")
    task_id = "migration-v1-" + "4" * 32

    class ToolsClient:
        def __init__(self) -> None:
            self.created = 0
            self.listed = 0

        def get_tool(self, request: object) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                tool_type="DevEnv",
                status="Ready",
                image_url="",
                envs=[
                    SimpleNamespace(key="CODEX_MODEL", value="doubao-test"),
                    SimpleNamespace(key="CODEX_API_KEY", value="secret"),
                    SimpleNamespace(key="CODEX_BASE_URL", value=base_url),
                ],
            )

        def list_sessions(self, request: object) -> SimpleNamespace:
            del request
            self.listed += 1
            return SimpleNamespace(
                session_infos=[
                    SimpleNamespace(
                        session_id="session-existing",
                        user_session_id=task_id,
                        endpoint="https://sandbox.invalid",
                        status="Ready",
                        created_at="2026-08-11T08:00:00Z",
                        expire_at="2026-08-11T09:00:00Z",
                        metadata=[SimpleNamespace(key="Username", value="owner-1")],
                    )
                ],
                next_token=None,
            )

        def create_session(self, request: object) -> SimpleNamespace:
            del request
            self.created += 1
            raise AssertionError("an idempotent retry must reuse the existing Session")

    client = ToolsClient()
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "volcengine")
    monkeypatch.setenv("CLOUD_PROVIDER", "volcengine")
    gateway = MigrationSandboxGateway(
        tool_id="tool-dev",
        region="cn-beijing",
        tools_client_factory=lambda region: client,
    )

    session = gateway.create_session(
        task_id=task_id,
        owner_id="owner-1",
        creator_name="Owner",
        display_name="存量迁移",
        ttl_seconds=3600,
    )

    assert session.session_id == "session-existing"
    assert client.listed == 1
    assert client.created == 0


def test_agentkit_gateway_waits_for_running_bash_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [
        {
            "data": {
                "session_id": "bash-session",
                "command_id": "command-1",
                "status": "running",
                "offset": 3,
                "stderr_offset": 1,
            }
        },
        {
            "data": {
                "session_id": "bash-session",
                "offset": 5,
                "stderr_offset": 2,
                "command": {
                    "command_id": "command-1",
                    "status": "running",
                    "exit_code": None,
                },
            }
        },
        {
            "data": {
                "session_id": "bash-session",
                "offset": 5,
                "stderr_offset": 2,
                "command": {
                    "command_id": "command-1",
                    "status": "completed",
                    "exit_code": 0,
                },
            }
        },
    ]
    calls: list[tuple[str, dict[str, object], object]] = []

    class Response:
        status_code = 200

        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def json(self) -> dict[str, object]:
            return self._payload

    def post(
        url: str,
        *,
        json: dict[str, object],
        timeout: object,
    ) -> Response:
        calls.append((url, json, timeout))
        return Response(responses.pop(0))

    monkeypatch.setattr("frontend.server.migration.gateway.requests.post", post)
    gateway = MigrationSandboxGateway(
        tool_id="tool-dev",
        region="cn-beijing",
        tools_client_factory=lambda region: None,
    )
    session = MigrationSandboxSession(
        tool_id="tool-dev",
        session_id="session-1",
        task_id="migration-v1-" + "1" * 32,
        endpoint="https://sandbox.invalid/proxy",
        region="cn-beijing",
        status="Ready",
        created_at="2026-08-11T08:00:00Z",
        expire_at="2026-08-11T09:00:00Z",
        owner_id="owner-1",
    )

    result = gateway.execute_bash(
        session,
        "prepare-project",
        operation="prepare_source",
        timeout_seconds=120,
    )

    assert result["status"] == "completed"
    assert [call[0] for call in calls] == [
        "https://sandbox.invalid/proxy/v1/bash/exec",
        "https://sandbox.invalid/proxy/v1/bash/output",
        "https://sandbox.invalid/proxy/v1/bash/output",
    ]
    assert calls[1][1] == {
        "session_id": "bash-session",
        "command_id": "command-1",
        "offset": 3,
        "stderr_offset": 1,
        "wait": True,
        "wait_timeout": 30,
    }
    assert calls[2][1]["offset"] == 5
    assert calls[2][1]["stderr_offset"] == 2


@pytest.mark.parametrize(
    ("status", "exit_code"),
    [
        ("completed", 1),
        ("timed_out", None),
        ("killed", None),
        ("unknown", None),
        ("", None),
    ],
)
def test_agentkit_gateway_rejects_unsuccessful_bash_terminal_states(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    exit_code: int | None,
) -> None:
    class Response:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {
                "data": {
                    "status": status,
                    "exit_code": exit_code,
                }
            }

    monkeypatch.setattr(
        "frontend.server.migration.gateway.requests.post",
        lambda *args, **kwargs: Response(),
    )
    gateway = MigrationSandboxGateway(
        tool_id="tool-dev",
        region="cn-beijing",
        tools_client_factory=lambda region: None,
    )
    session = MigrationSandboxSession(
        tool_id="tool-dev",
        session_id="session-1",
        task_id="migration-v1-" + "1" * 32,
        endpoint="https://sandbox.invalid/proxy",
        region="cn-beijing",
        status="Ready",
        created_at="2026-08-11T08:00:00Z",
        expire_at="2026-08-11T09:00:00Z",
        owner_id="owner-1",
    )

    with pytest.raises(MigrationGatewayError) as raised:
        gateway.execute_bash(
            session,
            "prepare-project",
            operation="prepare_source",
            timeout_seconds=120,
        )

    assert raised.value.code == "MIGRATION_REMOTE_EXEC_FAILED"
    assert raised.value.retryable is False


def test_agentkit_gateway_rejects_incomplete_running_bash_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {
                "data": {
                    "status": "running",
                    "session_id": "bash-session",
                    "offset": 0,
                    "stderr_offset": 0,
                }
            }

    monkeypatch.setattr(
        "frontend.server.migration.gateway.requests.post",
        lambda *args, **kwargs: Response(),
    )
    gateway = MigrationSandboxGateway(
        tool_id="tool-dev",
        region="cn-beijing",
        tools_client_factory=lambda region: None,
    )
    session = MigrationSandboxSession(
        tool_id="tool-dev",
        session_id="session-1",
        task_id="migration-v1-" + "1" * 32,
        endpoint="https://sandbox.invalid/proxy",
        region="cn-beijing",
        status="Ready",
        created_at="2026-08-11T08:00:00Z",
        expire_at="2026-08-11T09:00:00Z",
        owner_id="owner-1",
    )

    with pytest.raises(MigrationGatewayError) as raised:
        gateway.execute_bash(
            session,
            "prepare-project",
            operation="prepare_source",
            timeout_seconds=120,
        )

    assert raised.value.code == "MIGRATION_REMOTE_EXEC_INVALID"
    assert raised.value.retryable is False


def test_source_archive_validation_accepts_projects_and_rejects_unsafe_entries() -> (
    None
):
    accepted = validate_source_archive(
        source_zip({"agent.py": b"agent = object()\n", "README.md": b"demo\n"})
    )

    assert accepted.file_count == 2
    assert accepted.expanded_bytes == len(b"agent = object()\n") + len(b"demo\n")

    with pytest.raises(MigrationError, match="不安全路径"):
        validate_source_archive(source_zip({"../agent.py": b"x"}))
    with pytest.raises(MigrationError, match="不安全路径"):
        validate_source_archive(source_zip({"agent\r.py": b"x"}))
    with pytest.raises(MigrationError, match="符号链接"):
        validate_source_archive(source_zip({"agent.py": b"x"}, symlink="latest"))
    with pytest.raises(MigrationError, match="有效的 ZIP"):
        validate_source_archive(b"not-a-zip")


def test_upload_starts_read_only_codex_analysis_without_cli_inspection() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)

    task_id, uploaded = create_uploaded_task(service)

    assert uploaded["state"] == "analyzing"
    operations = [item[1] for item in gateway.commands]
    assert operations == ["accept_request", "prepare_source", "start_analysis"]
    assert gateway.command_timeouts == [
        ("accept_request", 30),
        ("prepare_source", 300),
        ("start_analysis", 30),
    ]
    analysis_command = gateway.commands[-1][2]
    assert "codex exec" in analysis_command
    assert "--sandbox read-only" in analysis_command
    assert "--output-schema" in analysis_command
    assert "--output-last-message" in analysis_command
    assert "ak migrate inspect" not in analysis_command
    assert f"{MIGRATION_ROOT}/input/project" in analysis_command
    assert "cleanup_analysis_start" in analysis_command
    assert "MIGRATION_ANALYSIS_START_FAILED" in analysis_command
    assert "command -v codex" in analysis_command
    assert "command -v setsid" in analysis_command
    syntax = subprocess.run(
        ["bash", "-n"],
        input=analysis_command,
        capture_output=True,
        check=False,
        text=True,
    )
    assert syntax.returncode == 0, syntax.stderr
    prompt = gateway.files[
        (task_id, f"{MIGRATION_ROOT}/state/analysis-prompt.md")
    ].decode()
    schema = json.loads(
        gateway.files[(task_id, f"{MIGRATION_ROOT}/state/analysis-schema.json")]
    )
    assert "只读" in prompt
    assert "证据" in prompt
    assert "用户使用什么语言" in prompt
    assert schema["properties"]["frameworks"]["maxItems"] == 20
    assert (
        schema["properties"]["frameworks"]["items"]["properties"]["evidence"][
            "maxItems"
        ]
        == 100
    )
    assert (
        schema["properties"]["frameworks"]["items"]["properties"]["evidence"]["items"][
            "properties"
        ]["path"]["maxLength"]
        == 4096
    )
    assert schema["properties"]["questions"]["maxItems"] == 50
    assert schema["properties"]["warnings"]["maxItems"] == 100


def test_upload_can_resume_analysis_start_after_source_was_accepted() -> None:
    class StartOnceGateway(FakeMigrationGateway):
        fail_start = True

        def execute_bash(
            self,
            session: MigrationSandboxSession,
            command: str,
            *,
            operation: str,
            timeout_seconds: int,
        ) -> dict[str, object]:
            if operation == "start_analysis" and self.fail_start:
                self.fail_start = False
                self.commands.append((session.task_id, operation, command))
                raise MigrationGatewayError(
                    "MIGRATION_REMOTE_EXEC_UNCERTAIN",
                    "Dev Sandbox 操作结果无法确认，请刷新迁移状态。",
                    retryable=False,
                )
            return super().execute_bash(
                session,
                command,
                operation=operation,
                timeout_seconds=timeout_seconds,
            )

    gateway = StartOnceGateway()
    service = MigrationService(gateway)
    created = service.create_task(
        CreateMigrationTaskBody(sourceFileName="support-agent.zip"),
        "owner-1",
        "Owner",
    )
    task_id = str(created["id"])
    source = source_zip()

    with pytest.raises(MigrationError) as uncertain:
        service.upload_source(task_id, "owner-1", source)

    recoverable = service.get_task(task_id, "owner-1")
    resumed = service.upload_source(task_id, "owner-1", source)

    assert uncertain.value.code == "MIGRATION_REMOTE_EXEC_UNCERTAIN"
    assert uncertain.value.retryable is False
    assert recoverable["state"] == "awaiting_upload"
    assert recoverable["canUpload"] is True
    assert resumed["state"] == "analyzing"
    assert [operation for _, operation, _ in gateway.commands] == [
        "accept_request",
        "prepare_source",
        "start_analysis",
        "start_analysis",
    ]


def test_analysis_result_rejects_unsafe_evidence_paths() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    mark_analysis_ready(gateway, task_id)
    invalid = analysis_result()
    frameworks = invalid["frameworks"]
    assert isinstance(frameworks, list)
    candidate = frameworks[0]
    assert isinstance(candidate, dict)
    evidence = candidate["evidence"]
    assert isinstance(evidence, list)
    assert isinstance(evidence[0], dict)
    evidence[0]["path"] = "../outside.py"
    gateway.files[(task_id, f"{MIGRATION_ROOT}/state/analysis.json")] = json.dumps(
        invalid, ensure_ascii=False
    ).encode()

    with pytest.raises(MigrationError) as raised:
        service.get_task(task_id, "owner-1")

    assert raised.value.code == "MIGRATION_ANALYSIS_INVALID"
    assert raised.value.retryable is False


@pytest.mark.parametrize(
    ("framework", "entry", "expected", "unexpected"),
    [
        (
            "langchain",
            "agent.py:agent",
            ["ak migrate", "--framework langchain", "--verify"],
            ["--execution in-place"],
        ),
        (
            "dify",
            None,
            [
                "ak migrate",
                "--framework dify",
                "--execution in-place",
                "--non-interactive",
                "--instruction-file",
            ],
            ["--verify"],
        ),
    ],
)
def test_confirmed_migration_uses_the_one_cli_contract(
    framework: str,
    entry: str | None,
    expected: list[str],
    unexpected: list[str],
) -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    mark_analysis_ready(gateway, task_id)

    started = service.confirm(
        task_id,
        "owner-1",
        ConfirmMigrationBody(
            framework=framework,
            entry=entry,
            appName="support-agent",
            instruction="迁移结果必须能在 AgentKit Runtime 中运行。",
            answers={},
        ),
    )

    assert started["state"] == "migrating"
    command = gateway.commands[-1][2]
    for fragment in expected:
        assert fragment in command
    for fragment in unexpected:
        assert fragment not in command
    assert f"--delivery-dir {MIGRATION_ROOT}/delivery" in command
    assert f"--provenance-file {MIGRATION_ROOT}/state/confirmation.json" in command
    assert f"--run-id {task_id}" in command
    assert gateway.command_timeouts[-1] == ("start_migration", 300)
    assert "cleanup_migration_start" in command
    assert f"{MIGRATION_ROOT}/state/migration-process-exit.json" in command
    assert "command -v ak" in command
    assert "command -v setsid" in command
    syntax = subprocess.run(
        ["bash", "-n"],
        input=command,
        capture_output=True,
        check=False,
        text=True,
    )
    assert syntax.returncode == 0, syntax.stderr
    confirmation = gateway.files[(task_id, f"{MIGRATION_ROOT}/state/confirmation.json")]
    assert hashlib.sha256(confirmation).hexdigest() in command
    confirmation_value = json.loads(confirmation)
    source_status = json.loads(
        gateway.files[(task_id, f"{MIGRATION_ROOT}/state/source.json")]
    )
    assert confirmation_value["source_archive_sha256"] == source_status["sha256"]


def test_running_task_rejects_source_or_decision_changes_and_can_stop() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    mark_analysis_ready(gateway, task_id)
    service.confirm(
        task_id,
        "owner-1",
        ConfirmMigrationBody(
            framework="langchain",
            entry="agent.py:agent",
            appName="support-agent",
            answers={},
        ),
    )

    with pytest.raises(MigrationError) as upload_error:
        service.upload_source(task_id, "owner-1", source_zip())
    with pytest.raises(MigrationError) as confirm_error:
        service.confirm(
            task_id,
            "owner-1",
            ConfirmMigrationBody(
                framework="langgraph",
                entry="graph.py:graph",
                appName="support-agent",
                answers={},
            ),
        )

    assert upload_error.value.status_code == 409
    assert confirm_error.value.status_code == 409
    stopped = service.stop(task_id, "owner-1")
    assert stopped["state"] == "cancelled"
    assert stopped["canModify"] is False
    stop_command = gateway.commands[-1][2]
    assert "root_marker" in stop_command
    assert "pid does not belong to this migration" in stop_command


def test_service_recovers_terminal_state_and_verified_artifact_from_session() -> None:
    gateway = FakeMigrationGateway()
    first_service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(first_service)
    mark_analysis_ready(gateway, task_id)
    first_service.confirm(
        task_id,
        "owner-1",
        ConfirmMigrationBody(
            framework="langchain",
            entry="agent.py:agent",
            appName="support-agent",
            answers={},
        ),
    )
    report_content = b'{"status":"succeeded"}\n'
    artifact = artifact_zip(
        {
            "agentkit_app.py": b"app = object()\n",
            ".agentkit/migration-plan.json": report_content,
        }
    )
    artifact_sha = hashlib.sha256(artifact).hexdigest()
    preview_content = b"app = object()\n"
    result = {
        "schema_version": 1,
        "run_id": task_id,
        "cli": {"name": "agentkit-cli", "version": "0.52.0"},
        "migration": {
            "engine": "structured",
            "framework": "langchain",
            "entry": "agent.py:agent",
            "source_sha256": "1" * 64,
            "provenance_sha256": hashlib.sha256(
                gateway.files[(task_id, f"{MIGRATION_ROOT}/state/confirmation.json")]
            ).hexdigest(),
        },
        "status": "succeeded",
        "files": [
            {
                "path": "agentkit_app.py",
                "size": len(preview_content),
                "sha256": hashlib.sha256(preview_content).hexdigest(),
                "mode": "0644",
            },
            {
                "path": ".agentkit/migration-plan.json",
                "size": len(report_content),
                "sha256": hashlib.sha256(report_content).hexdigest(),
                "mode": "0644",
            },
        ],
        "startup": {"module": "agentkit_app.py", "object": "app"},
        "environment": {"required": ["MODEL_AGENT_API_KEY"], "optional": []},
        "verification": {
            "status": "passed",
            "checks": [{"name": "import", "status": "passed"}],
        },
        "warnings": [],
        "report": {"path": ".agentkit/migration-plan.json"},
        "artifact": {
            "path": "migration-result.zip",
            "size": len(artifact),
            "sha256": artifact_sha,
        },
        "created_at": "2026-08-11T08:20:00Z",
    }
    gateway.files[(task_id, f"{MIGRATION_ROOT}/delivery/migration-result.json")] = (
        json.dumps(result).encode()
    )
    gateway.files[(task_id, f"{MIGRATION_ROOT}/delivery/migration-result.zip")] = (
        artifact
    )
    gateway.files[(task_id, f"{MIGRATION_ROOT}/workspace/source/agentkit_app.py")] = (
        preview_content
    )
    gateway.files[(task_id, f"{MIGRATION_ROOT}/delivery/migration-status.json")] = (
        json.dumps(
            {
                "schema_version": 1,
                "run_id": task_id,
                "sequence": 4,
                "state": "succeeded",
                "phase": "completed",
                "message": "Migration artifact is ready",
                "artifact": {
                    "state": "ready",
                    "preview_ready": True,
                    "download_ready": True,
                    "deploy_ready": True,
                },
                "updated_at": "2026-08-11T08:20:00Z",
            }
        ).encode()
    )

    recovered_service = MigrationService(gateway)
    task = recovered_service.get_task(task_id, "owner-1")
    manifest = recovered_service.artifact(task_id, "owner-1")
    preview, media_type = recovered_service.preview_file(
        task_id,
        "owner-1",
        "agentkit_app.py",
    )
    downloaded, filename = recovered_service.download(task_id, "owner-1")

    assert task["state"] == "succeeded"
    assert task["artifact"]["previewReady"] is True
    assert task["artifact"]["deployReady"] is True
    assert manifest["cli"]["version"] == "0.52.0"
    assert preview == preview_content
    assert media_type == "text/x-python"
    assert downloaded == artifact
    assert filename == "support-agent-migrated.zip"

    result["migration"]["provenance_sha256"] = "0" * 64
    gateway.files[(task_id, f"{MIGRATION_ROOT}/delivery/migration-result.json")] = (
        json.dumps(result).encode()
    )
    with pytest.raises(MigrationError) as mismatched:
        recovered_service.artifact(task_id, "owner-1")
    assert mismatched.value.code == "MIGRATION_ARTIFACT_PROVENANCE_MISMATCH"

    result["migration"]["provenance_sha256"] = hashlib.sha256(
        gateway.files[(task_id, f"{MIGRATION_ROOT}/state/confirmation.json")]
    ).hexdigest()

    result["files"][0]["path"] = "generated//agentkit_app.py"
    result["startup"]["module"] = "generated//agentkit_app.py"
    gateway.files[(task_id, f"{MIGRATION_ROOT}/delivery/migration-result.json")] = (
        json.dumps(result).encode()
    )
    with pytest.raises(MigrationError) as unsafe_path:
        recovered_service.artifact(task_id, "owner-1")
    assert unsafe_path.value.code == "MIGRATION_ARTIFACT_INVALID"

    result["files"][0]["path"] = "agentkit_app.py"
    result["startup"]["module"] = "agentkit_app.py"
    result["artifact"]["size"] = True
    gateway.files[(task_id, f"{MIGRATION_ROOT}/delivery/migration-result.json")] = (
        json.dumps(result).encode()
    )
    with pytest.raises(MigrationError) as boolean_size:
        recovered_service.artifact(task_id, "owner-1")
    assert boolean_size.value.code == "MIGRATION_ARTIFACT_INVALID"

    result["artifact"]["size"] = len(artifact)
    result["report"]["path"] = "missing-report.md"
    gateway.files[(task_id, f"{MIGRATION_ROOT}/delivery/migration-result.json")] = (
        json.dumps(result).encode()
    )
    with pytest.raises(MigrationError) as missing_report:
        recovered_service.artifact(task_id, "owner-1")
    assert missing_report.value.code == "MIGRATION_ARTIFACT_INVALID"

    result["report"]["path"] = ".agentkit/migration-plan.json"
    result["verification"]["status"] = "unknown"
    gateway.files[(task_id, f"{MIGRATION_ROOT}/delivery/migration-result.json")] = (
        json.dumps(result).encode()
    )
    with pytest.raises(MigrationError) as invalid_verification:
        recovered_service.artifact(task_id, "owner-1")
    assert invalid_verification.value.code == "MIGRATION_ARTIFACT_INVALID"

    result["verification"]["status"] = "passed"
    gateway.files[(task_id, f"{MIGRATION_ROOT}/delivery/migration-result.json")] = (
        json.dumps(result).encode()
    )
    gateway.files[(task_id, f"{MIGRATION_ROOT}/state/source.json")] = gateway.files[
        (task_id, f"{MIGRATION_ROOT}/state/source.json")
    ].replace(
        json.loads(gateway.files[(task_id, f"{MIGRATION_ROOT}/state/source.json")])[
            "sha256"
        ].encode(),
        b"0" * 64,
    )
    with pytest.raises(MigrationError) as wrong_source:
        recovered_service.artifact(task_id, "owner-1")
    assert wrong_source.value.code == "MIGRATION_ARTIFACT_SOURCE_MISMATCH"


def test_materialize_deployment_requires_deploy_ready_and_owner_verified_artifact(
    tmp_path: Path,
) -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    mark_analysis_ready(gateway, task_id)
    service.confirm(
        task_id,
        "owner-1",
        ConfirmMigrationBody(
            framework="langchain",
            entry="agent.py:agent",
            appName="support-agent",
            answers={},
        ),
    )
    project_files = {
        "runtime/agentkit_app.py": b"app = object()\n",
        "agentkit.yaml": (
            b"common:\n  agent_name: support-agent\n"
            b"  entry_point: runtime/agentkit_app.py\n"
        ),
    }
    artifact = artifact_zip(project_files)
    result = {
        "schema_version": 1,
        "run_id": task_id,
        "cli": {"name": "agentkit-cli", "version": "0.52.0"},
        "migration": {
            "engine": "structured",
            "framework": "langchain",
            "entry": "agent.py:agent",
            "source_sha256": "1" * 64,
            "provenance_sha256": hashlib.sha256(
                gateway.files[(task_id, f"{MIGRATION_ROOT}/state/confirmation.json")]
            ).hexdigest(),
        },
        "status": "succeeded",
        "files": [
            {
                "path": path,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "mode": "0644",
            }
            for path, content in project_files.items()
        ],
        "startup": {"module": "runtime/agentkit_app.py", "object": "app"},
        "environment": {"required": [], "optional": []},
        "verification": {
            "status": "passed",
            "checks": [{"name": "import", "status": "passed"}],
        },
        "warnings": [],
        "report": {"path": "agentkit.yaml"},
        "artifact": {
            "path": "migration-result.zip",
            "size": len(artifact),
            "sha256": hashlib.sha256(artifact).hexdigest(),
        },
        "created_at": "2026-08-11T08:20:00Z",
    }
    gateway.files[(task_id, f"{MIGRATION_ROOT}/delivery/migration-result.json")] = (
        json.dumps(result).encode()
    )
    gateway.files[(task_id, f"{MIGRATION_ROOT}/delivery/migration-result.zip")] = (
        artifact
    )
    status_path = f"{MIGRATION_ROOT}/delivery/migration-status.json"
    gateway.files[(task_id, status_path)] = json.dumps(
        {
            "schema_version": 1,
            "run_id": task_id,
            "sequence": 4,
            "state": "succeeded",
            "phase": "completed",
            "message": "Migration artifact is ready",
            "artifact": {
                "state": "ready",
                "preview_ready": True,
                "download_ready": True,
                "deploy_ready": False,
            },
            "updated_at": "2026-08-11T08:20:00Z",
        }
    ).encode()

    with pytest.raises(MigrationError) as not_ready:
        service.materialize_deployment(task_id, "owner-1", tmp_path)
    with pytest.raises(MigrationError) as wrong_owner:
        service.materialize_deployment(task_id, "owner-2", tmp_path)

    gateway.files[(task_id, status_path)] = gateway.files[
        (task_id, status_path)
    ].replace(b'"deploy_ready": false', b'"deploy_ready": true')
    target = tmp_path / "deploy"
    target.mkdir()
    entry_point = service.materialize_deployment(
        task_id,
        "owner-1",
        target,
    )

    assert not_ready.value.code == "MIGRATION_ARTIFACT_NOT_DEPLOYABLE"
    assert not_ready.value.retryable is False
    assert wrong_owner.value.status_code == 404
    assert entry_point == "runtime/agentkit_app.py"
    assert (target / entry_point).read_bytes() == project_files[entry_point]
    assert (target / "agentkit.yaml").read_bytes() == project_files["agentkit.yaml"]


def test_materialize_deployment_rejects_archive_that_does_not_match_manifest(
    tmp_path: Path,
) -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    mark_analysis_ready(gateway, task_id)
    service.confirm(
        task_id,
        "owner-1",
        ConfirmMigrationBody(
            framework="any",
            entry=None,
            appName="support-agent",
            answers={},
        ),
    )
    content = b"app = object()\n"
    artifact = artifact_zip({"app.py": b"tampered\n"})
    result = {
        "schema_version": 1,
        "run_id": task_id,
        "cli": {"name": "agentkit-cli", "version": "0.52.0"},
        "migration": {
            "engine": "agentic",
            "framework": "any",
            "source_sha256": "1" * 64,
            "provenance_sha256": hashlib.sha256(
                gateway.files[(task_id, f"{MIGRATION_ROOT}/state/confirmation.json")]
            ).hexdigest(),
        },
        "status": "succeeded",
        "files": [
            {
                "path": "app.py",
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "mode": "0644",
            }
        ],
        "startup": {"module": "app.py", "object": "app"},
        "environment": {"required": [], "optional": []},
        "verification": {"status": "passed", "checks": []},
        "warnings": [],
        "report": {"path": "app.py"},
        "artifact": {
            "path": "migration-result.zip",
            "size": len(artifact),
            "sha256": hashlib.sha256(artifact).hexdigest(),
        },
        "created_at": "2026-08-11T08:20:00Z",
    }
    gateway.files[(task_id, f"{MIGRATION_ROOT}/delivery/migration-result.json")] = (
        json.dumps(result).encode()
    )
    gateway.files[(task_id, f"{MIGRATION_ROOT}/delivery/migration-result.zip")] = (
        artifact
    )
    gateway.files[(task_id, f"{MIGRATION_ROOT}/delivery/migration-status.json")] = (
        json.dumps(
            {
                "schema_version": 1,
                "run_id": task_id,
                "sequence": 4,
                "state": "succeeded",
                "phase": "completed",
                "message": "Migration artifact is ready",
                "artifact": {
                    "state": "ready",
                    "preview_ready": True,
                    "download_ready": True,
                    "deploy_ready": True,
                },
                "updated_at": "2026-08-11T08:20:00Z",
            }
        ).encode()
    )

    with pytest.raises(MigrationError) as raised:
        service.materialize_deployment(task_id, "owner-1", tmp_path)

    assert raised.value.code == "MIGRATION_ARTIFACT_INTEGRITY_FAILED"
    assert raised.value.retryable is False


def test_ready_session_is_expired_at_its_ttl_deadline() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(
        gateway,
        clock=lambda: datetime(
            2026,
            8,
            11,
            9,
            0,
            tzinfo=timezone.utc,
        ).timestamp(),
    )
    created = service.create_task(
        CreateMigrationTaskBody(sourceFileName="support-agent.zip"),
        "owner-1",
        "Owner",
    )
    task_id = str(created["id"])
    gateway.sessions[task_id] = replace(
        gateway.sessions[task_id],
        created_at="2026-08-11T08:00:00Z",
        expire_at="2026-08-11T09:00:00Z",
        status="Ready",
        endpoint="https://sandbox.invalid",
    )

    task = service.get_task(task_id, "owner-1")

    assert task["state"] == "expired"
    assert task["artifact"]["previewReady"] is False
    assert task["artifact"]["downloadReady"] is False
    assert task["artifact"]["deployReady"] is False


def test_product_ttl_does_not_follow_a_later_platform_expiry() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(
        gateway,
        clock=lambda: datetime(
            2026,
            8,
            11,
            9,
            0,
            tzinfo=timezone.utc,
        ).timestamp(),
    )
    created = service.create_task(
        CreateMigrationTaskBody(sourceFileName="support-agent.zip"),
        "owner-1",
        "Owner",
    )
    task_id = str(created["id"])
    gateway.sessions[task_id] = replace(
        gateway.sessions[task_id],
        created_at="2026-08-11T08:00:00Z",
        expire_at="2026-08-11T10:00:00Z",
        status="Ready",
        endpoint="https://sandbox.invalid",
    )

    task = service.get_task(task_id, "owner-1")

    assert task["state"] == "expired"
    assert task["expiresAt"] == "2026-08-11T09:00:00Z"


def test_completed_process_without_delivery_state_does_not_stay_running() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    mark_analysis_ready(gateway, task_id)
    service.confirm(
        task_id,
        "owner-1",
        ConfirmMigrationBody(
            framework="langchain",
            entry="agent.py:agent",
            appName="support-agent",
            answers={},
        ),
    )
    gateway.files.pop((task_id, f"{MIGRATION_ROOT}/delivery/migration-status.json"))
    gateway.files[(task_id, f"{MIGRATION_ROOT}/state/migration-process-exit.json")] = (
        json.dumps({"schema_version": 1, "exit_code": 0}).encode()
    )

    task = service.get_task(task_id, "owner-1")

    assert task["state"] == "failed"
    assert task["error"]["code"] == "MIGRATION_DELIVERY_MISSING"
    assert task["error"]["retryable"] is False


def test_terminal_delivery_requires_a_ready_artifact_contract() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    mark_analysis_ready(gateway, task_id)
    service.confirm(
        task_id,
        "owner-1",
        ConfirmMigrationBody(
            framework="langchain",
            entry="agent.py:agent",
            appName="support-agent",
            answers={},
        ),
    )
    gateway.files[(task_id, f"{MIGRATION_ROOT}/delivery/migration-status.json")] = (
        json.dumps(
            {
                "schema_version": 1,
                "run_id": task_id,
                "sequence": 4,
                "state": "succeeded",
                "phase": "completed",
                "message": "Migration artifact is ready",
                "artifact": {
                    "state": "ready",
                    "preview_ready": False,
                    "download_ready": True,
                    "deploy_ready": True,
                },
                "updated_at": "2026-08-11T08:20:00Z",
            }
        ).encode()
    )

    with pytest.raises(MigrationError) as raised:
        service.get_task(task_id, "owner-1")

    assert raised.value.code == "MIGRATION_DELIVERY_INVALID"
    assert raised.value.retryable is False


def test_completed_analysis_without_terminal_state_does_not_stay_running() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    gateway.files[(task_id, f"{MIGRATION_ROOT}/state/analysis-process-exit.json")] = (
        json.dumps({"schema_version": 1, "exit_code": 0}).encode()
    )

    task = service.get_task(task_id, "owner-1")

    assert task["state"] == "failed"
    assert task["error"]["code"] == "MIGRATION_ANALYSIS_RESULT_MISSING"
    assert task["error"]["retryable"] is False


def test_broken_session_does_not_fail_the_entire_task_list() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    healthy = service.create_task(
        CreateMigrationTaskBody(sourceFileName="support-agent.zip"),
        "owner-1",
        "Owner",
    )
    broken_id = "migration-v1-" + "f" * 32
    gateway.sessions[broken_id] = MigrationSandboxSession(
        tool_id="tool-dev",
        session_id="session-broken",
        task_id=broken_id,
        endpoint="https://sandbox.invalid",
        region="cn-beijing",
        status="Ready",
        created_at="2099-01-01T00:00:00Z",
        expire_at="2099-01-01T01:00:00Z",
        owner_id="owner-1",
    )

    listed = service.list_tasks("owner-1")["items"]

    assert {task["id"] for task in listed} == {healthy["id"], broken_id}
    broken = next(task for task in listed if task["id"] == broken_id)
    assert broken["state"] == "failed"
    assert broken["error"]["retryable"] is False


def test_expired_remote_session_is_read_only_and_does_not_fake_retryability() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    gateway.sessions[task_id] = replace(
        gateway.sessions[task_id],
        status="Expired",
        endpoint="",
    )

    task = service.get_task(task_id, "owner-1")

    assert task["state"] == "expired"
    assert task["canModify"] is False
    assert task["artifact"]["downloadReady"] is False
    with pytest.raises(MigrationError) as raised:
        service.stop(task_id, "owner-1")
    assert raised.value.retryable is False


def test_migration_routes_enforce_upload_boundary_and_owner_identity() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    app = FastAPI()

    def owner(request: Request) -> str:
        assert request.headers["x-test-owner"] == "owner-1"
        return "owner-1"

    mount_migration_routes(
        app,
        service,
        owner_resolver=owner,
        creator_resolver=lambda request: "Owner",
    )
    client = TestClient(app)
    headers = {"x-test-owner": "owner-1"}

    capability = client.get("/web/migrations/capabilities", headers=headers)
    created = client.post(
        "/web/migrations/tasks",
        headers=headers,
        json={
            "taskId": "migration-v1-" + "9" * 32,
            "sourceFileName": "support-agent.zip",
            "instruction": "保留客服流程。",
        },
    )
    task_id = created.json()["id"]

    wrong_type = client.put(
        f"/web/migrations/tasks/{task_id}/source",
        headers={**headers, "content-type": "text/plain"},
        content=b"not-a-zip",
    )
    too_large = client.put(
        f"/web/migrations/tasks/{task_id}/source",
        headers={
            **headers,
            "content-type": "application/zip",
            "content-length": str(MIGRATION_UPLOAD_MAX_BYTES + 1),
        },
        content=b"",
    )
    uploaded = client.put(
        f"/web/migrations/tasks/{task_id}/source",
        headers={**headers, "content-type": "application/zip"},
        content=source_zip(),
    )

    assert capability.status_code == 200
    assert capability.json()["maxUploadBytes"] == MIGRATION_UPLOAD_MAX_BYTES
    assert created.status_code == 200
    assert wrong_type.status_code == 415
    assert wrong_type.json()["detail"]["retryable"] is False
    assert too_large.status_code == 413
    assert too_large.json()["detail"]["code"] == "MIGRATION_SOURCE_TOO_LARGE"
    assert uploaded.status_code == 200
    assert uploaded.json()["state"] == "analyzing"


def test_confirm_request_rejects_an_entry_outside_the_project() -> None:
    with pytest.raises(ValueError):
        ConfirmMigrationBody(
            framework="langchain",
            entry="../outside.py:agent",
            appName="support-agent",
            answers={},
        )
