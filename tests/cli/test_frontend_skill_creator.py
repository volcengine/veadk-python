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
import stat
import time
import zipfile

from types import SimpleNamespace
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
        assert model_base_url == "https://credential-relay.example.com/api/v3"
        calls.append((candidate_id, model))
        return {"instanceId": f"instance-{candidate_id}", "endpoint": "endpoint"}

    with (
        patch.object(
            service,
            "_validate_tool",
            return_value="https://credential-relay.example.com/api/v3",
        ),
        patch.object(service, "_create_candidate", side_effect=create_candidate),
    ):
        result = service.create_job("Create a release notes Skill", "alice")

    assert result["status"] == "running"
    assert {candidate["id"] for candidate in result["candidates"]} == {"a", "b"}
    assert set(calls) == {
        ("a", "doubao-seed-2-0-pro-260215"),
        ("b", "deepseek-v4-flash-260425"),
    }


def test_runner_uses_prompt_file_and_ephemeral_codex() -> None:
    source = _runner_source()

    assert 'job_dir / "prompt.txt"' in source
    assert '"--ephemeral"' in source
    assert '"workspace-write"' in source
    assert '"--dangerously-bypass-approvals-and-sandbox"' not in source
    assert "secret_values" in source
    assert "ck-test-ticket" not in source


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
            return_value="https://credential-relay.example.com/api/v3",
        ),
        patch.object(service, "_create_candidate", side_effect=create_candidate),
        patch.object(service, "_delete_instances") as delete_instances,
        pytest.raises(SkillCreatorError, match="创建 AgentKit Sandbox 会话失败"),
    ):
        service.create_job("Create a release notes Skill", "alice")

    delete_instances.assert_called_once_with([("tool-id", "instance-b")])


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


def test_credential_hosting_is_bound_to_tool_without_raw_key() -> None:
    class FakeApi:
        def call(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            return {
                "Tool": {
                    "Envs": [
                        {"Key": "CODEX_API_KEY", "Value": "raw-key"},
                        {"Key": "CODEX_BASE_URL", "Value": "https://ark.example"},
                    ]
                }
            }

    updates: dict[str, str] = {}
    with (
        patch("agentkit.auth._openapi.OpenApiClient", return_value=FakeApi()),
        patch(
            "agentkit.auth.credential_hosting.list_gateways",
            return_value=[{"id": "gateway-id", "name": "agentkit-credhost-gw"}],
        ),
        patch("veadk.auth.veauth.ark_veauth.get_ark_token", return_value="raw-key"),
        patch(
            "agentkit.auth.credential_hosting.host_model_key",
            return_value=SimpleNamespace(
                ticket="ck-hosted-ticket",
                model_base_url="https://credential-relay.example.com/api/v3",
            ),
        ),
        patch(
            "agentkit.auth.credential_hosting.set_tool_env",
            side_effect=lambda _api, _tool_id, values: updates.update(values),
        ),
    ):
        ensure_skill_creator_model_credential(
            tool_id="tool-id",
            access_key="access-key",
            secret_key="secret-key",
        )

    assert updates["CODEX_API_KEY"] == "ck-hosted-ticket"
    assert updates["CODEX_BASE_URL"] == ("https://credential-relay.example.com/api/v3")
    assert "raw-key" not in updates.values()


def test_routes_mount_and_report_disabled_without_sandbox(monkeypatch) -> None:
    monkeypatch.delenv("VEADK_SKILL_CREATOR_TOOL_ID", raising=False)
    monkeypatch.delenv("AGENTKIT_SANDBOX_TOOL_ID", raising=False)
    app = FastAPI()
    mount_skill_creator_routes(app, lambda request: "test-user")

    response = TestClient(app).get("/web/skill-creator/capabilities")

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert len(response.json()["models"]) == 2
