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

"""Tests for the Sandbox-backed frontend Skill creator."""

import io
import json
import os
import stat
import subprocess
import sys
import time
import zipfile

from types import SimpleNamespace
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from veadk.cli.frontend_skill_creator import (
    SkillCreatorError,
    SkillCreatorService,
    _runner_source,
    ensure_skill_creator_model_credential,
    mount_skill_creator_routes,
)

_MODEL_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"


def _skill_zip(name: str = "weather-report") -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            f"{name}/SKILL.md",
            "\n".join(
                [
                    "---",
                    f"name: {name}",
                    "description: Build a concise weather report.",
                    "---",
                    "",
                    "# Weather report",
                ]
            ),
        )
    return output.getvalue()


def test_job_id_is_bound_to_owner() -> None:
    service = SkillCreatorService(tool_id="tool-id")
    job_id = service._new_job_id("alice")

    service._validate_job_owner(job_id, "alice")
    with pytest.raises(SkillCreatorError, match="无权访问"):
        service._validate_job_owner(job_id, "bob")


def test_archive_metadata_requires_safe_single_matching_root() -> None:
    service = SkillCreatorService(tool_id="tool-id")

    assert service._archive_metadata(_skill_zip()) == (
        "weather-report",
        "Build a concise weather report.",
    )

    unsafe = io.BytesIO()
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../SKILL.md", "invalid")
    with pytest.raises(SkillCreatorError, match="不安全路径"):
        service._archive_metadata(unsafe.getvalue())


def test_create_job_runs_fixed_models_in_independent_candidates() -> None:
    service = SkillCreatorService(tool_id="tool-id")
    calls: list[tuple[str, str]] = []
    progress: list[dict[str, Any]] = []

    def create_candidate(
        tool_id: str,
        job_id: str,
        candidate_id: str,
        model: str,
        label: str,
        model_base_url: str,
        request: str,
    ) -> dict[str, str]:
        del tool_id, job_id, label, request
        assert model_base_url == _MODEL_BASE_URL
        calls.append((candidate_id, model))
        return {"instanceId": f"instance-{candidate_id}", "endpoint": "endpoint"}

    with (
        patch.object(
            service,
            "_validate_tool",
            return_value=_MODEL_BASE_URL,
        ),
        patch.object(service, "_create_candidate", side_effect=create_candidate),
    ):
        result = service.create_job(
            "Create a release notes Skill", "alice", progress.append
        )

    assert result["status"] == "running"
    assert {candidate["id"] for candidate in result["candidates"]} == {"a", "b"}
    assert set(calls) == {
        ("a", "doubao-seed-2-0-pro-260215"),
        ("b", "deepseek-v4-flash-260425"),
    }
    assert len(progress) == 3
    assert all(snapshot["status"] == "provisioning" for snapshot in progress)
    assert all(
        candidate["activities"][0]["text"] == "正在拉起 Sandbox"
        for candidate in progress[0]["candidates"]
    )
    assert any(
        candidate["activities"][0]["text"] == "Sandbox 已就绪，正在启动生成"
        for candidate in progress[1]["candidates"]
    )
    assert all(candidate["status"] == "running" for candidate in result["candidates"])


def test_new_session_visibility_is_retried_before_job_becomes_running() -> None:
    service = SkillCreatorService(tool_id="tool-id")
    session = {"instanceId": "instance-a", "endpoint": "https://sandbox"}

    with (
        patch.object(
            service,
            "_find_session",
            side_effect=[SkillCreatorError("Skill 创建任务不存在或已过期"), session],
        ) as find_session,
        patch("veadk.cli.frontend_skill_creator.time.sleep") as sleep,
    ):
        service._wait_for_session_visibility("tool-id", "job-a")

    assert find_session.call_count == 2
    sleep.assert_called_once_with(5.0)


def test_runner_uses_prompt_file_and_ephemeral_codex() -> None:
    source = _runner_source()

    assert 'job_dir / "prompt.txt"' in source
    assert '"--ephemeral"' in source
    assert '"workspace-write"' in source
    assert '"--json"' in source
    assert "subprocess.Popen" in source
    assert "handle_event(json.loads(line))" in source
    assert '"--dangerously-bypass-approvals-and-sandbox"' not in source
    assert "secret_values" in source
    assert "redact(traceback.format_exc())" in source
    assert "sensitive_assignment.sub" in source
    assert "ck-test-ticket" not in source


def test_runner_streams_only_public_bounded_activities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = tmp_path / "runner.py"
    runner.write_text(_runner_source(), encoding="utf-8")
    (tmp_path / "prompt.txt").write_text("Create a safe Skill", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import pathlib\n"
        "import sys\n"
        "work = pathlib.Path(sys.argv[sys.argv.index('-C') + 1])\n"
        "root = work / 'weather-report'\n"
        "root.mkdir(parents=True)\n"
        "(root / 'SKILL.md').write_text(\n"
        "    '---\\nname: weather-report\\ndescription: Weather report.\\n---\\n',\n"
        "    encoding='utf-8',\n"
        ")\n"
        "events = [\n"
        "  {'type': 'item.completed', 'item': {'id': 'thinking', 'type': 'reasoning', 'summary': ['检查 Skill 结构', '准备生成文件']}},\n"
        "  {'type': 'item.started', 'item': {'id': 'cmd', 'type': 'command_execution', 'command': 'python /home/gem/.codex/build.py'}},\n"
        "  {'type': 'item.completed', 'item': {'id': 'cmd', 'type': 'command_execution', 'command': 'python /home/gem/.codex/build.py', 'status': 'completed'}},\n"
        "  {'type': 'item.completed', 'item': {'id': 'write', 'type': 'command_execution', 'command': 'cat > /home/gem/jobs/work/weather-report/SKILL.md'}},\n"
        "  {'type': 'item.completed', 'item': {'id': 'file', 'type': 'file_change', 'path': 'weather-report/SKILL.md'}},\n"
        "  {'type': 'item.completed', 'item': {'id': 'mcp', 'type': 'mcp_tool_call', 'server': 'files', 'tool': 'inspect', 'arguments': {'api_key': 'plain-secret'}, 'result': {'ok': True}}},\n"
        "  {'type': 'item.completed', 'item': {'id': 'message', 'type': 'agent_message', 'text': 'Skill 已生成'}},\n"
        "]\n"
        "for event in events:\n"
        "    print(json.dumps(event), flush=True)\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")

    subprocess.run([sys.executable, str(runner)], check=True)

    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    serialized = json.dumps(status["activities"], ensure_ascii=False)
    assert status["status"] == "succeeded"
    assert "检查 Skill 结构" in serialized
    assert "准备生成文件" in serialized
    assert "运行校验脚本" in serialized
    assert "修改文件" in serialized
    assert ".codex" not in serialized.lower()
    assert "plain-secret" not in serialized
    assert "MCP · files/inspect" in serialized
    assert "weather-report/SKILL.md" in serialized
    assert "Skill 已生成" in serialized
    assert all(
        len(json.dumps(item, ensure_ascii=False)) <= 4_500
        for item in status["activities"]
    )
    assert len(status["activities"]) <= 80


def test_runner_redacts_environment_and_structured_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = tmp_path / "runner.py"
    runner.write_text(_runner_source(), encoding="utf-8")
    (tmp_path / "prompt.txt").write_text("Create a safe Skill", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        "#!/bin/sh\n"
        'echo "api_key=$MODEL_API_KEY"\n'
        'echo "password=third-party-password"\n'
        "exit 1\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    monkeypatch.setenv("MODEL_API_KEY", "sk-raw-runner-key")
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")

    subprocess.run([sys.executable, str(runner)], check=True)

    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    error_log = (tmp_path / "runner-error.log").read_text(encoding="utf-8")
    serialized = json.dumps(status, ensure_ascii=False) + error_log
    assert status["status"] == "failed"
    assert "BrokenPipeError" not in serialized
    assert "sk-raw-runner-key" not in serialized
    assert "third-party-password" not in serialized
    assert "[REDACTED]" in serialized


def test_create_job_cleans_up_successful_candidate_when_peer_fails() -> None:
    service = SkillCreatorService(tool_id="tool-id")

    def create_candidate(*args: object, **kwargs: object) -> dict[str, str]:
        del kwargs
        candidate_id = str(args[2])
        if candidate_id == "a":
            raise RuntimeError("candidate failed")
        time.sleep(0.02)
        return {"instanceId": "instance-b", "endpoint": "endpoint"}

    with (
        patch.object(
            service,
            "_validate_tool",
            return_value=_MODEL_BASE_URL,
        ),
        patch.object(service, "_create_candidate", side_effect=create_candidate),
        patch.object(service, "_delete_instances") as delete_instances,
        pytest.raises(SkillCreatorError, match="创建 AgentKit Sandbox 会话失败"),
    ):
        service.create_job("Create a release notes Skill", "alice")

    delete_instances.assert_called_once_with([("tool-id", "instance-b")])


def test_candidate_status_rejects_invalid_or_oversized_activities() -> None:
    service = SkillCreatorService(tool_id="tool-id")
    oversized = [
        {"id": f"event-{index}", "kind": "status", "text": "ok", "status": "done"}
        for index in range(81)
    ]
    remote_status = {
        "status": "running",
        "stage": "generating",
        "activities": oversized,
    }
    with (
        patch.object(
            service,
            "_find_session",
            return_value={"instanceId": "instance-a", "endpoint": "https://sandbox"},
        ),
        patch("veadk.cli.frontend_skill_creator.requests.post"),
        patch(
            "veadk.cli.frontend_skill_creator._safe_json_response",
            return_value={"data": {"output": json.dumps(remote_status)}},
        ),
        pytest.raises(SkillCreatorError, match="活动记录格式错误"),
    ):
        service._candidate_status("tool-id", "job-id", "a", "model", "label")


def test_archive_metadata_rejects_symlink_entry() -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "weather-report/SKILL.md",
            "---\nname: weather-report\ndescription: Weather.\n---\n",
        )
        link = zipfile.ZipInfo("weather-report/link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "../../secret")

    with pytest.raises(SkillCreatorError, match="符号链接"):
        SkillCreatorService(tool_id="tool-id")._archive_metadata(output.getvalue())


def test_model_credential_is_bound_directly_to_tool() -> None:
    access_key = os.urandom(16).hex()
    model_api_key = os.urandom(24).hex()
    secret_key = os.urandom(24).hex()
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeApi:
        def call(
            self,
            _service: str,
            action: str,
            _version: str,
            body: dict[str, object],
        ) -> dict[str, object]:
            calls.append((action, body))
            if action == "GetTool":
                return {
                    "Tool": {"Envs": [{"Key": "EXISTING_ENV", "Value": "preserved"}]}
                }
            return {}

    with (
        patch("agentkit.auth._openapi.OpenApiClient", return_value=FakeApi()),
        patch(
            "veadk.auth.veauth.ark_veauth.get_ark_token",
            return_value=model_api_key,
        ) as get_ark_token,
    ):
        ensure_skill_creator_model_credential(
            tool_id="tool-id",
            access_key=access_key,
            secret_key=secret_key,
        )

    get_ark_token.assert_called_once_with(
        region="cn-beijing",
        access_key=access_key,
        secret_key=secret_key,
        session_token=None,
    )
    assert [action for action, _ in calls] == ["GetTool", "UpdateTool"]
    update_body = calls[1][1]
    envs = {
        item["Key"]: item["Value"]
        for item in cast(list[dict[str, str]], update_body["Envs"])
    }
    assert envs["EXISTING_ENV"] == "preserved"
    assert envs["CODEX_API_KEY"] == model_api_key
    assert envs["CODEX_BASE_URL"] == _MODEL_BASE_URL


def test_candidate_session_never_overrides_tool_model_credential(monkeypatch) -> None:
    service = SkillCreatorService(tool_id="tool-id")
    captured: dict[str, object] = {}

    class FakeClient:
        def create_session(self, request: object) -> SimpleNamespace:
            captured["request"] = request
            return SimpleNamespace(session_id="instance-a", endpoint="https://sandbox")

        def delete_session(self, _request: object) -> None:
            pass

    monkeypatch.setenv("MODEL_API_KEY", "sk-raw-studio-process-key")
    with (
        patch(
            "veadk.cli.frontend_skill_creator.AgentkitToolsClient",
            return_value=FakeClient(),
        ),
        patch.object(service, "_wait_for_session_visibility"),
        patch("veadk.cli.frontend_skill_creator.requests.post"),
        patch("veadk.cli.frontend_skill_creator._safe_json_response", return_value={}),
    ):
        service._create_candidate(
            "tool-id",
            service._new_job_id("alice"),
            "a",
            "doubao-seed-2-0-pro-260215",
            "豆包 Seed 2.0 Pro",
            _MODEL_BASE_URL,
            "Create a release notes Skill",
        )

    request = cast(Any, captured["request"])
    envs = {item.key: item.value for item in request.envs}
    assert "sk-raw-studio-process-key" not in envs.values()
    assert {"CODEX_API_KEY", "OPENCODE_API_KEY", "ANTHROPIC_AUTH_TOKEN"}.isdisjoint(
        envs
    )


def test_tool_rejects_untrusted_model_base_url() -> None:
    service = SkillCreatorService(tool_id="tool-id")
    tool = SimpleNamespace(
        tool_type="CodeEnv",
        status="Ready",
        envs=[
            SimpleNamespace(key="CODEX_API_KEY", value=os.urandom(24).hex()),
            SimpleNamespace(
                key="CODEX_BASE_URL", value="http://attacker.invalid/api/v3"
            ),
        ],
    )
    with (
        patch("veadk.cli.frontend_skill_creator.AgentkitToolsClient") as client_class,
        pytest.raises(SkillCreatorError, match="模型服务地址无效"),
    ):
        client_class.return_value.get_tool.return_value = tool
        service._validate_tool("tool-id")


def test_routes_mount_and_report_disabled_without_sandbox(monkeypatch) -> None:
    monkeypatch.delenv("SANDBOX_SKILL_CREATOR", raising=False)
    monkeypatch.delenv("VEADK_SKILL_CREATOR_TOOL_ID", raising=False)
    monkeypatch.delenv("AGENTKIT_SANDBOX_TOOL_ID", raising=False)
    app = FastAPI()
    mount_skill_creator_routes(app, lambda request: "test-user")

    response = TestClient(app).get("/web/skill-creator/capabilities")

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["reason"] == "管理员未配置"
    assert len(response.json()["models"]) == 2


def test_skill_creator_reads_only_dedicated_sandbox_tool_env(monkeypatch) -> None:
    monkeypatch.setenv("SANDBOX_SKILL_CREATOR", "skill-creator-tool")
    monkeypatch.setenv("VEADK_SKILL_CREATOR_TOOL_ID", "legacy-tool")
    monkeypatch.setenv("AGENTKIT_SANDBOX_TOOL_ID", "shared-tool")

    assert SkillCreatorService()._tool_id() == "skill-creator-tool"

    monkeypatch.delenv("SANDBOX_SKILL_CREATOR")
    with pytest.raises(SkillCreatorError, match="管理员未配置"):
        SkillCreatorService()._tool_id()


def test_skill_creator_uses_configured_sandbox_region(monkeypatch) -> None:
    monkeypatch.setenv("AGENTKIT_SANDBOX_REGION", "cn-shanghai")
    tool = SimpleNamespace(
        tool_type="CodeEnv",
        status="Ready",
        envs=[
            SimpleNamespace(key="CODEX_API_KEY", value=os.urandom(24).hex()),
            SimpleNamespace(key="CODEX_BASE_URL", value=_MODEL_BASE_URL),
        ],
    )
    with patch("veadk.cli.frontend_skill_creator.AgentkitToolsClient") as client_class:
        client_class.return_value.get_tool.return_value = tool

        SkillCreatorService(tool_id="tool-id")._validate_tool("tool-id")

    client_class.assert_called_once_with(region="cn-shanghai")
