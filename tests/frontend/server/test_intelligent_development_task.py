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

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest
import yaml

from frontend.server import intelligent_development_task as task_module
from frontend.server.intelligent_development import StudioCredentials
from frontend.server.intelligent_development import REMOTE_DELIVERY_WORKER
from frontend.server.intelligent_development_task import (
    DeliveryPublisher,
    TaskCredentialLease,
    builder_prompt,
    create_credential_lease,
    parse_completion_contract,
    parse_intent_decision,
)


def test_intent_parser_accepts_only_bounded_typed_decisions() -> None:
    decision = parse_intent_decision(
        json.dumps(
            {
                "decision": "accept",
                "message": "",
                "intentSummary": "构建天气 Agent",
                "acceptanceCriteria": ["返回天气和数据时间"],
                "changesDelivery": True,
            },
            ensure_ascii=False,
        )
    )
    assert decision.decision == "accept"
    assert decision.changes_delivery is True
    with pytest.raises(ValueError):
        parse_intent_decision('{"decision":"accept"}')
    with pytest.raises(ValueError, match="acceptance context"):
        parse_intent_decision(
            json.dumps(
                {
                    "decision": "accept",
                    "message": "",
                    "intentSummary": "构建天气 Agent",
                    "acceptanceCriteria": [],
                    "changesDelivery": True,
                },
                ensure_ascii=False,
            )
        )


def test_verified_completion_requires_all_cloud_and_cleanup_gates() -> None:
    gates = {
        name: True
        for name in (
            "local-checks",
            "service-probe",
            "ak-config",
            "ak-build",
            "ak-deploy",
            "runtime-ready",
            "acceptance-invoke",
            "runtime-logs",
            "runtime-cleanup",
        )
    }
    value = {
        "schemaVersion": "1",
        "status": "verified",
        "summary": "全部通过",
        "runtimeName": "idv-weather-123",
        "attemptCount": 1,
        "gates": gates,
        "acceptanceCriteria": ["返回天气和数据时间"],
    }
    assert parse_completion_contract(json.dumps(value).encode()).verified is True
    value["gates"]["runtime-cleanup"] = False
    with pytest.raises(ValueError, match="incomplete"):
        parse_completion_contract(json.dumps(value).encode())


def test_builder_context_uses_launcher_without_secret_values() -> None:
    decision = parse_intent_decision(
        json.dumps(
            {
                "decision": "accept",
                "message": "",
                "intentSummary": "构建天气 Agent",
                "acceptanceCriteria": ["返回天气"],
                "changesDelivery": True,
            }
        )
    )
    prompt = builder_prompt(
        "做一个天气 Agent",
        decision,
        launcher_path="/secure/task/launcher",
        completion_path="/workspace/completion.json",
        expire_at="2026-08-15T08:00:00Z",
        remaining_lifetime_minutes=417,
        validation_region="cn-beijing",
        validation_project="default",
    )
    assert "Use the preinstalled veadk-agent-development Skill" in prompt
    assert "$veadk-agent-development" not in prompt
    assert "injected Skill" not in prompt
    assert "/secure/task/launcher" in prompt
    assert "VOLCENGINE_SECRET_KEY" not in prompt
    assert "production deployment" in prompt
    assert "417 whole minutes" in prompt
    assert "authoritative" in prompt
    assert "cn-beijing" in prompt
    assert 'existing AgentKit project "default"' in prompt
    assert "do not derive project_name" in prompt
    assert "Do not stop at scaffolding, local checks, or a successful build" in prompt
    assert "coherent, runnable, deployable" in prompt
    assert "use `ak init --template agent_server` by default" in prompt
    assert "accepted user intent explicitly requires a different" in prompt
    assert "Do not default to the `basic` template" in prompt
    assert "concise user-facing summary" in prompt
    assert "entire final assistant response" not in prompt
    assert "If time is running short" not in prompt
    assert "Studio" not in prompt
    assert "Sandbox" not in prompt


@pytest.mark.asyncio
async def test_credentials_are_uploaded_once_outside_workspace_and_cleaned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Remote:
        instances: list["Remote"] = []

        def __init__(self, endpoint: str) -> None:
            self.endpoint = endpoint
            self.commands: list[str] = []
            self.uploads: list[tuple[str, bytes, int | None]] = []
            self.instances.append(self)

        async def exec_text(self, command: str, *, timeout: int = 12) -> str:
            del timeout
            self.commands.append(command)
            return ""

        async def upload(
            self,
            path: str,
            content: bytes,
            *,
            media_type: str = "application/octet-stream",
            max_bytes: int = 20 * 1024 * 1024,
            mode: int | None = None,
        ) -> None:
            del media_type, max_bytes
            self.uploads.append((path, content, mode))

    monkeypatch.setattr(task_module, "SandboxRemoteTransport", Remote)
    lease = await create_credential_lease(
        "https://sandbox.example/session",
        lambda: StudioCredentials("ACCESS_EXACT", "SECRET_EXACT", "TOKEN_EXACT"),
    )
    remote = Remote.instances[0]
    assert lease.root.startswith("/home/gem/.intelligent-development/tasks/")
    assert all(
        not path.startswith("/home/gem/workspace/") for path, _, _ in remote.uploads
    )
    credential = next(
        item for item in remote.uploads if item[0].endswith("credentials.json")
    )
    launcher = next(
        item for item in remote.uploads if item[0].endswith("with-agentkit-credentials")
    )
    assert credential[2] == 0o600
    assert b"ACCESS_EXACT" in credential[1]
    assert launcher[2] == 0o700
    assert b"ACCESS_EXACT" not in launcher[1]
    assert b"SECRET_EXACT" not in launcher[1]
    await lease.cleanup()
    assert any("task secrets remain" in command for command in remote.commands)


@pytest.mark.asyncio
async def test_failed_credential_cleanup_can_be_retried() -> None:
    class Remote:
        def __init__(self) -> None:
            self.calls = 0

        async def exec_text(self, command: str, *, timeout: int = 12) -> str:
            del command, timeout
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary cleanup failure")
            return ""

    remote = Remote()
    lease = TaskCredentialLease(
        remote,  # type: ignore[arg-type]
        "/home/gem/.intelligent-development/tasks/retry",
        "/home/gem/.intelligent-development/tasks/retry/launcher",
        "/home/gem/.intelligent-development/tasks/retry/credentials.json",
        ("secret",),
    )

    with pytest.raises(RuntimeError, match="credential cleanup failed"):
        await lease.cleanup()
    await lease.cleanup()
    assert remote.calls == 2


@pytest.mark.asyncio
async def test_delivery_publisher_sends_server_parsed_manifest_contract() -> None:
    manifest = b"common:\n  agent_name: weather\n  entry_point: weather.py\n"
    artifact_digest = "a" * 64
    report_digest = "b" * 64
    release = (
        f"/home/gem/.intelligent-development/releases/{artifact_digest}-{report_digest}"
    )

    class Remote:
        def __init__(self) -> None:
            self.downloads: list[tuple[str, int]] = []
            self.uploads: dict[str, tuple[bytes, int | None]] = {}
            self.commands: list[tuple[str, int]] = []

        async def download(self, path: str, *, max_bytes: int) -> bytes:
            self.downloads.append((path, max_bytes))
            return manifest

        async def upload(
            self,
            path: str,
            content: bytes,
            *,
            media_type: str = "application/octet-stream",
            max_bytes: int = 20 * 1024 * 1024,
            mode: int | None = None,
        ) -> None:
            del media_type, max_bytes
            self.uploads[path] = (content, mode)

        async def exec_json(self, command: str, *, timeout: int) -> dict[str, object]:
            self.commands.append((command, timeout))
            return {
                "sessionId": "session",
                "artifactSha256": artifact_digest,
                "artifactSize": 128,
                "agentName": "weather",
                "entryPoint": "weather.py",
                "fileCount": 2,
                "artifactPath": f"{release}/artifact.zip",
                "descriptorPath": f"{release}/descriptor.json",
                "validationReportPath": (f"{release}/validation/{report_digest}.json"),
                "validationReportSha256": report_digest,
                "releasePath": release,
            }

        async def exec_text(self, command: str, *, timeout: int) -> str:
            self.commands.append((command, timeout))
            return ""

    completion = parse_completion_contract(
        json.dumps(
            {
                "schemaVersion": "1",
                "status": "verified",
                "summary": "全部通过",
                "runtimeName": "idv-weather-123",
                "attemptCount": 1,
                "gates": {
                    name: True
                    for name in (
                        "local-checks",
                        "service-probe",
                        "ak-config",
                        "ak-build",
                        "ak-deploy",
                        "runtime-ready",
                        "acceptance-invoke",
                        "runtime-logs",
                        "runtime-cleanup",
                    )
                },
                "acceptanceCriteria": ["返回天气"],
            }
        ).encode()
    )
    remote = Remote()

    delivery = await DeliveryPublisher(remote).publish(  # type: ignore[arg-type]
        session_id="session",
        project_root="/home/gem/workspace/session",
        task_root="/home/gem/.intelligent-development/tasks/task",
        completion=completion,
        exact_secrets=("SECRET_EXACT",),
    )

    assert remote.downloads == [
        ("/home/gem/workspace/session/agentkit.yaml", 256 * 1024)
    ]
    request_path = next(
        path
        for path in remote.uploads
        if path.endswith(".json") and "secrets" not in path
    )
    request = json.loads(remote.uploads[request_path][0])
    assert request["projectRoot"] == "/home/gem/workspace/session"
    assert request["agentName"] == "weather"
    assert request["entryPoint"] == "weather.py"
    assert request["manifestSha256"] == hashlib.sha256(manifest).hexdigest()
    assert set(request) == {
        "projectRoot",
        "report",
        "secretPath",
        "agentName",
        "entryPoint",
        "manifestSha256",
    }
    secret_path = request["secretPath"]
    assert remote.uploads[secret_path] == (b'["SECRET_EXACT"]', 0o600)
    assert delivery.agent_name == "weather"
    assert delivery.entry_point == "weather.py"
    assert delivery.artifact_sha256 == artifact_digest
    assert delivery.validation_report_sha256 == report_digest
    assert delivery.deployable is True
    assert delivery.verified is True

    source_only = await DeliveryPublisher(remote).publish(  # type: ignore[arg-type]
        session_id="session",
        project_root="/home/gem/workspace/session",
        task_root="/home/gem/.intelligent-development/tasks/task",
        completion=None,
        exact_secrets=("SECRET_EXACT",),
        acceptance_criteria=("返回天气",),
    )
    requests = [
        json.loads(content)
        for path, (content, _mode) in remote.uploads.items()
        if path.endswith(".json") and "secrets" not in path
    ]
    unverified_request = next(
        item for item in requests if item["report"]["status"] == "unverified"
    )
    assert unverified_request["report"]["acceptanceCriteria"] == ["返回天气"]
    assert unverified_request["report"]["validationSummary"] == "未收到完整验证结果"
    assert source_only.deployable is True
    assert source_only.verified is False
    assert source_only.gate_summary == ()


def _run_delivery_worker(
    tmp_path: Path,
    *,
    files: dict[str, bytes],
    secrets: tuple[str, ...] = (),
    report: dict[str, object] | None = None,
) -> subprocess.CompletedProcess[str]:
    workspace_root = tmp_path / "workspace"
    project = workspace_root / "session"
    state_root = tmp_path / "state"
    project.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    worker = tmp_path / "delivery-worker.py"
    worker.write_text(
        REMOTE_DELIVERY_WORKER.replace(
            'ROOT = Path("/home/gem/.intelligent-development")',
            f"ROOT = Path({str(state_root)!r})",
        ).replace(
            'WORKSPACES = Path("/home/gem/workspace")',
            f"WORKSPACES = Path({str(workspace_root)!r})",
        ),
        encoding="utf-8",
    )
    secret_path = tmp_path / "secrets.json"
    secret_path.write_text(json.dumps(list(secrets)), encoding="utf-8")
    os.chmod(secret_path, 0o600)
    request = tmp_path / "request.json"
    manifest_bytes = files["agentkit.yaml"]
    manifest = yaml.safe_load(manifest_bytes)
    common = manifest["common"]
    request.write_text(
        json.dumps(
            {
                "projectRoot": str(project),
                "report": report or {"sessionId": "session"},
                "secretPath": str(secret_path),
                "agentName": common["agent_name"],
                "entryPoint": common["entry_point"],
                "manifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return subprocess.run(
        [sys.executable, "-I", "-S", str(worker), str(request)],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_delivery_worker_packages_final_project_and_excludes_local_state(
    tmp_path: Path,
) -> None:
    result = _run_delivery_worker(
        tmp_path,
        files={
            "agentkit.yaml": (
                b"common:\n  agent_name: weather\n  entry_point: weather.py\n"
            ),
            "weather.py": b"root_agent = object()\n",
            ".env.example": b"MODEL_API_KEY=replace-me\n",
            ".agentkit/artifacts/build.log": b"cloud build evidence\n",
            ".studio-intelligent-development-result.json": b"{}",
        },
    )
    assert result.returncode == 0, result.stderr
    descriptor = json.loads(result.stdout)
    artifact = Path(descriptor["artifactPath"])
    with zipfile.ZipFile(artifact) as archive:
        assert sorted(archive.namelist()) == [
            ".env.example",
            "agentkit.yaml",
            "weather.py",
        ]


def test_delivery_worker_rejects_supplied_credentials(tmp_path: Path) -> None:
    result = _run_delivery_worker(
        tmp_path,
        files={
            "agentkit.yaml": (
                b"common:\n  agent_name: weather\n  entry_point: weather.py\n"
            ),
            "weather.py": b"TOKEN = 'SECRET_EXACT'\n",
        },
        secrets=("SECRET_EXACT",),
    )
    assert result.returncode != 0
    assert "supplied credentials" in result.stderr


@pytest.mark.parametrize("name", [".ssh/id_rsa", "private.pem"])
def test_delivery_worker_rejects_credential_files(tmp_path: Path, name: str) -> None:
    result = _run_delivery_worker(
        tmp_path,
        files={
            "agentkit.yaml": (
                b"common:\n  agent_name: weather\n  entry_point: weather.py\n"
            ),
            "weather.py": b"root_agent = object()\n",
            name: b"not-for-delivery",
        },
    )
    assert result.returncode != 0
    assert "forbidden credential" in result.stderr


def test_delivery_worker_keeps_revalidations_of_identical_source_immutable(
    tmp_path: Path,
) -> None:
    files = {
        "agentkit.yaml": (
            b"common:\n  agent_name: weather\n  entry_point: weather.py\n"
        ),
        "weather.py": b"root_agent = object()\n",
    }
    first = _run_delivery_worker(
        tmp_path,
        files=files,
        report={"sessionId": "session", "validatedAt": "2026-08-16T00:00:00Z"},
    )
    second = _run_delivery_worker(
        tmp_path,
        files=files,
        report={"sessionId": "session", "validatedAt": "2026-08-16T00:01:00Z"},
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    first_descriptor = json.loads(first.stdout)
    second_descriptor = json.loads(second.stdout)
    assert first_descriptor["artifactSha256"] == second_descriptor["artifactSha256"]
    assert (
        first_descriptor["validationReportSha256"]
        != second_descriptor["validationReportSha256"]
    )
    assert first_descriptor["releasePath"] != second_descriptor["releasePath"]
