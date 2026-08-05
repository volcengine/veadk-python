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

import io
import stat
import zipfile
from types import SimpleNamespace

import pytest

from veadk.cli.frontend_skill_workbench import (
    CreateSkillTaskBody,
    PublishSkillTaskBody,
    SkillWorkbenchError,
    SkillWorkbenchService,
    build_delegation_brief,
    validate_skill_archive,
)


def skill_zip(
    name: str = "release-notes",
    *,
    description: str = "Create concise release notes.",
    extra: dict[str, str] | None = None,
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            f"{name}/SKILL.md",
            f"---\nname: {name}\ndescription: {description}\n---\n\n# Instructions\n",
        )
        for path, content in (extra or {}).items():
            archive.writestr(f"{name}/{path}", content)
    return output.getvalue()


def test_delegation_brief_delegates_outcome_without_dictating_steps() -> None:
    brief = build_delegation_brief(
        "optimize",
        "Make failures actionable while preserving the public contract.",
        source_path="/workspace/source.zip",
        revision=2,
    )

    assert "$skill-creator" in brief
    assert "Make failures actionable" in brief
    assert "Independently inspect" in brief
    assert "Source: /workspace/source.zip" in brief
    assert "run this command" not in brief.lower()
    assert "step 1" not in brief.lower()
    assert "cat >" not in brief


@pytest.mark.parametrize(
    ("operation", "source", "message"),
    [
        (
            "create",
            {"kind": "skill-center", "skillId": "s", "version": "1"},
            "不接受来源",
        ),
        ("optimize", None, "必须选择来源"),
    ],
)
def test_request_requires_source_only_for_optimization(
    operation: str, source: dict[str, str] | None, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        CreateSkillTaskBody.model_validate(
            {"operation": operation, "intent": "Improve it", "source": source}
        )


def test_validate_skill_archive_returns_normalized_metadata() -> None:
    content = skill_zip(extra={"references/checklist.md": "# Checklist\n"})

    archive = validate_skill_archive(content)

    assert archive.name == "release-notes"
    assert archive.description == "Create concise release notes."
    assert archive.skill_md.startswith("---")
    assert archive.sha256
    assert archive.files == [
        {"path": "SKILL.md", "size": len(archive.skill_md.encode("utf-8"))},
        {
            "path": "references/checklist.md",
            "size": len("# Checklist\n".encode("utf-8")),
        },
    ]


@pytest.mark.parametrize(
    ("builder", "code"),
    [
        (
            lambda z: z.writestr("../SKILL.md", "bad"),
            "SKILL_ARCHIVE_UNSAFE_PATH",
        ),
        (
            lambda z: (
                z.writestr("one/SKILL.md", "---\nname: one\ndescription: One.\n---\n"),
                z.writestr("two/file.md", "bad"),
            ),
            "SKILL_ARCHIVE_MULTIPLE_ROOTS",
        ),
        (
            lambda z: (
                z.writestr("one/SKILL.md", "---\nname: one\ndescription: One.\n---\n"),
                _write_symlink(z, "one/link"),
            ),
            "SKILL_ARCHIVE_SYMLINK",
        ),
    ],
)
def test_validate_skill_archive_rejects_unsafe_boundaries(builder, code: str) -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        builder(archive)

    with pytest.raises(SkillWorkbenchError) as caught:
        validate_skill_archive(output.getvalue())

    assert caught.value.code == code


def _write_symlink(archive: zipfile.ZipFile, name: str) -> None:
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    archive.writestr(info, "target")


def test_capabilities_fail_closed_without_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SANDBOX_SKILL_WORKBENCH", raising=False)
    monkeypatch.delenv("SANDBOX_SKILL_CREATOR", raising=False)

    value = SkillWorkbenchService().capabilities()

    assert value == {
        "enabled": False,
        "reason": "管理员未配置 DevEnv Tool",
        "operations": ["create", "optimize"],
    }


def test_capabilities_require_ready_devenv_and_optional_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VEADK_SKILL_DEVENV_IMAGE", "registry/dev:1")
    tools = SimpleNamespace(
        get_tool=lambda request: SimpleNamespace(
            tool_type="DevEnv",
            status="Ready",
            image_url="registry/dev:1",
        )
    )
    service = SkillWorkbenchService(
        tool_id="tool-1", tools_client_factory=lambda region: tools
    )

    value = service.capabilities()

    assert value["enabled"] is True
    assert value["reason"] == ""
    assert value["maxUploadBytes"] == 5 * 1024 * 1024


def test_job_id_hides_cross_owner_resources() -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")

    SkillWorkbenchService._validate_job_owner(job_id, "alice")
    with pytest.raises(SkillWorkbenchError) as caught:
        SkillWorkbenchService._validate_job_owner(job_id, "bob")

    assert caught.value.code == "SKILL_TASK_NOT_FOUND"
    assert caught.value.status_code == 404


def test_list_tasks_filters_owner_projects_summaries_and_sorts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alice_new = SkillWorkbenchService._new_job_id("alice")
    alice_old = SkillWorkbenchService._new_job_id("alice")
    bob_job = SkillWorkbenchService._new_job_id("bob")
    requests = []
    pages = [
        SimpleNamespace(
            session_infos=[
                _session(alice_old, "alice", "old-endpoint"),
                _session(bob_job, "bob", "bob-endpoint"),
                _session("unrelated", "alice", "other-endpoint"),
            ],
            next_token="page-2",
        ),
        SimpleNamespace(
            session_infos=[_session(alice_new, "alice", "new-endpoint")],
            next_token=None,
        ),
    ]

    class Tools:
        def list_sessions(self, request):
            requests.append(request)
            return pages.pop(0)

    service = SkillWorkbenchService(
        tool_id="tool", tools_client_factory=lambda region: Tools()
    )
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")
    tasks = {
        alice_old: {
            "jobId": alice_old,
            "operation": "create",
            "intent": "Old intent",
            "revision": 1,
            "state": "running",
            "stage": "generating",
            "createdAt": 10,
            "activities": [{"private": True}],
            "skillMd": "secret detail",
            "files": [{"path": "SKILL.md"}],
        },
        alice_new: {
            "jobId": alice_new,
            "operation": "optimize",
            "intent": "New intent",
            "revision": 2,
            "state": "ready",
            "stage": "packaging",
            "createdAt": 20,
            "name": "new-skill",
            "source": {"name": "source-skill", "sha256": "private"},
            "validation": {"valid": True},
        },
    }
    monkeypatch.setattr(
        service,
        "_task_from_session",
        lambda endpoint, job_id: tasks[job_id],
    )

    result = service.list_tasks("alice")

    assert [task["jobId"] for task in result["tasks"]] == [alice_new, alice_old]
    assert result["tasks"][0] == {
        "jobId": alice_new,
        "operation": "optimize",
        "intent": "New intent",
        "revision": 2,
        "state": "ready",
        "stage": "packaging",
        "createdAt": 20,
        "name": "new-skill",
        "sourceName": "source-skill",
    }
    assert "activities" not in result["tasks"][1]
    assert "skillMd" not in result["tasks"][1]
    assert "files" not in result["tasks"][1]
    assert requests[0].metadata[0].key == "Username"
    assert requests[0].metadata[0].value == "alice"
    assert requests[1].next_token == "page-2"


def test_list_tasks_rejects_repeated_pagination_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = SimpleNamespace(session_infos=[], next_token="same-token")
    tools = SimpleNamespace(list_sessions=lambda request: response)
    service = SkillWorkbenchService(
        tool_id="tool", tools_client_factory=lambda region: tools
    )
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")

    with pytest.raises(SkillWorkbenchError) as caught:
        service.list_tasks("alice")

    assert caught.value.code == "SKILL_TASK_LIST_INVALID"
    assert caught.value.retryable is True


def test_task_state_normalization_is_shared_by_detail_and_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    service = SkillWorkbenchService(tool_id="tool")
    payloads = {
        "request.json": {
            "jobId": job_id,
            "operation": "create",
            "intent": "Create it",
            "revision": 1,
            "createdAt": 1,
        },
        "status.json": {"status": "succeeded", "stage": "packaging"},
    }
    monkeypatch.setattr(
        service,
        "_remote_json",
        lambda endpoint, requested_job_id, filename: payloads[filename],
    )

    detail = service._task_from_session("endpoint", job_id)

    assert detail["state"] == "ready"
    assert service._task_summary(detail)["state"] == "ready"


def _session(job_id: str, owner: str, endpoint: str) -> SimpleNamespace:
    return SimpleNamespace(
        user_session_id=job_id,
        endpoint=endpoint,
        metadata=[{"Key": "Username", "Value": owner}],
    )


def test_upload_source_is_allowed_only_for_optimization() -> None:
    service = SkillWorkbenchService(tool_id="tool")
    body = CreateSkillTaskBody(operation="create", intent="Build a Skill")

    with pytest.raises(SkillWorkbenchError, match="仅可作为优化来源") as caught:
        service.create_task(body, "alice", "Alice", uploaded_archive=skill_zip())

    assert caught.value.status_code == 422


def test_publish_update_requires_trusted_center_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    monkeypatch.setattr(
        service,
        "get_task",
        lambda job_id, owner_id: {
            "jobId": job_id,
            "state": "ready",
            "revision": 1,
            "source": {"kind": "upload", "name": "release-notes"},
        },
    )
    body = PublishSkillTaskBody(
        disposition="update-source",
        expectedRevision=1,
    )

    with pytest.raises(SkillWorkbenchError) as caught:
        service.publish(service._new_job_id("alice"), "alice", body)

    assert caught.value.code == "SKILL_UPDATE_NOT_ALLOWED"
    assert caught.value.status_code == 409


def test_publish_rejects_stale_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    monkeypatch.setattr(
        service,
        "get_task",
        lambda job_id, owner_id: {
            "jobId": job_id,
            "state": "ready",
            "revision": 3,
            "source": None,
        },
    )
    body = PublishSkillTaskBody(
        disposition="create-new",
        expectedRevision=2,
    )

    with pytest.raises(SkillWorkbenchError) as caught:
        service.publish(service._new_job_id("alice"), "alice", body)

    assert caught.value.code == "SKILL_TASK_REVISION_CONFLICT"
