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
import json
import stat
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from veadk.cli.frontend_skill_workbench import (
    CreateSkillTaskBody,
    PublishSkillTaskBody,
    SkillWorkbenchError,
    SkillWorkbenchService,
    build_delegation_brief,
    mount_skill_workbench_routes,
    validate_skill_archive,
)


def skill_zip(
    name: str = "release-notes",
    *,
    description: str = "Create concise release notes.",
    extra: dict[str, str] | None = None,
    member_prefix: str = "",
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            f"{member_prefix}{name}/SKILL.md",
            f"---\nname: {name}\ndescription: {description}\n---\n\n# Instructions\n",
        )
        for path, content in (extra or {}).items():
            archive.writestr(f"{member_prefix}{name}/{path}", content)
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


def test_create_request_rejects_an_optimization_source() -> None:
    with pytest.raises(ValueError, match="不接受来源"):
        CreateSkillTaskBody.model_validate(
            {
                "operation": "create",
                "intent": "Create it",
                "source": {
                    "kind": "skill-center",
                    "skillId": "s",
                    "version": "1",
                },
            }
        )


def test_optimization_requires_a_center_source_or_uploaded_archive() -> None:
    service = SkillWorkbenchService(tool_id="tool")
    body = CreateSkillTaskBody(operation="optimize", intent="Improve it")

    with pytest.raises(SkillWorkbenchError, match="必须选择来源或上传 ZIP") as caught:
        service.create_task(body, "alice", "Alice")

    assert caught.value.code == "SKILL_SOURCE_REQUIRED"
    assert caught.value.status_code == 422


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


def test_validate_skill_archive_rejects_invalid_zip() -> None:
    with pytest.raises(SkillWorkbenchError) as caught:
        validate_skill_archive(b"not-a-zip")

    assert caught.value.code == "SKILL_ARCHIVE_INVALID"


def test_validate_skill_archive_rejects_suspicious_compression_ratio() -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "compressed/SKILL.md",
            "---\nname: compressed\ndescription: Compressed input.\n---\n"
            + ("x" * (512 * 1024)),
        )

    with pytest.raises(SkillWorkbenchError) as caught:
        validate_skill_archive(output.getvalue())

    assert caught.value.code == "SKILL_ARCHIVE_SUSPICIOUS_COMPRESSION"
    assert caught.value.status_code == 413


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
    assert value["maxUploadBytes"] == 20 * 1024 * 1024


def test_reserve_task_returns_owner_bound_id_without_agentkit() -> None:
    service = SkillWorkbenchService(
        tool_id="tool",
        tools_client_factory=lambda region: pytest.fail("AgentKit must not be called"),
    )

    reservation = service.reserve_task("alice")

    reserved_at = reservation["reservedAt"]
    assert isinstance(reserved_at, int)
    assert reserved_at > 0
    SkillWorkbenchService._validate_job_owner(str(reservation["jobId"]), "alice")


def test_supplied_job_id_is_validated_before_source_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")

    def resolve_source(source):
        pytest.fail("source must not be resolved")

    monkeypatch.setattr(service, "_resolve_center_source", resolve_source)
    body = CreateSkillTaskBody.model_validate(
        {
            "operation": "optimize",
            "intent": "Improve it",
            "source": {
                "kind": "skill-center",
                "skillId": "skill",
                "version": "1",
            },
            "jobId": SkillWorkbenchService._new_job_id("bob"),
        }
    )

    with pytest.raises(SkillWorkbenchError) as caught:
        service.create_task(body, "alice", "Alice")

    assert caught.value.code == "SKILL_TASK_NOT_FOUND"


def test_supplied_durable_job_id_returns_existing_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    service = SkillWorkbenchService(
        tool_id="tool",
        tools_client_factory=lambda region: pytest.fail("must not create Session"),
    )
    existing = {"jobId": job_id, "state": "running"}
    monkeypatch.setattr(service, "get_task", lambda requested, owner: existing)
    body = CreateSkillTaskBody(operation="create", intent="Create", jobId=job_id)

    assert service.create_task(body, "alice", "Alice") is existing


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


def test_list_tasks_returns_expired_session_without_reading_released_devenv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    response = SimpleNamespace(
        session_infos=[
            _session(
                job_id,
                "alice",
                "released-endpoint",
                status="Ready",
                expire_at="2000-01-01T00:00:00Z",
                created_at="1999-12-31T23:00:00Z",
            )
        ],
        next_token=None,
    )
    tools = SimpleNamespace(list_sessions=lambda request: response)
    service = SkillWorkbenchService(
        tool_id="tool", tools_client_factory=lambda region: tools
    )
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")
    monkeypatch.setattr(
        service,
        "_task_from_session",
        lambda endpoint, requested_job_id: pytest.fail(
            "an expired DevEnv must not be contacted"
        ),
    )

    result = service.list_tasks("alice")

    assert result == {
        "tasks": [
            {
                "jobId": job_id,
                "operation": "create",
                "intent": "Skill 会话",
                "revision": 1,
                "state": "expired",
                "stage": "expired",
                "createdAt": 946681200,
            }
        ]
    }


def test_find_session_distinguishes_expired_from_missing() -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    response = SimpleNamespace(
        session_infos=[
            _session(
                job_id,
                "alice",
                "released-endpoint",
                status="Expired",
                expire_at="2000-01-01T00:00:00Z",
            )
        ]
    )
    tools = SimpleNamespace(list_sessions=lambda request: response)
    service = SkillWorkbenchService(
        tool_id="tool", tools_client_factory=lambda region: tools
    )

    with pytest.raises(SkillWorkbenchError) as caught:
        service._find_session("tool", job_id)

    assert caught.value.code == "SKILL_TASK_EXPIRED"
    assert caught.value.status_code == 410
    assert str(caught.value) == "DevEnv 已到期并自动释放"


def test_delete_task_is_idempotent_after_devenv_expiration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    service = SkillWorkbenchService(
        tool_id="tool",
        tools_client_factory=lambda region: pytest.fail(
            "an expired Session has no remote resource to delete"
        ),
    )
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")

    def expired_session(tool_id: str, requested_job_id: str) -> dict[str, str]:
        raise SkillWorkbenchError(
            "SKILL_TASK_EXPIRED",
            "DevEnv 已到期并自动释放",
            status_code=410,
        )

    monkeypatch.setattr(service, "_find_session", expired_session)

    service.delete_task(job_id, "alice")


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
    assert detail["sessionTtlSeconds"] == 3600
    assert service._task_summary(detail)["state"] == "ready"


def test_get_task_returns_the_live_session_expiration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    service = SkillWorkbenchService(tool_id="tool")
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")
    monkeypatch.setattr(
        service,
        "_find_session",
        lambda tool_id, requested_job_id: {
            "instanceId": "session-1",
            "endpoint": "https://devenv.example",
            "expireAt": "2026-08-05T12:00:00Z",
        },
    )
    monkeypatch.setattr(
        service,
        "_task_from_session",
        lambda endpoint, requested_job_id: {
            "jobId": requested_job_id,
            "operation": "create",
            "intent": "Create it",
            "revision": 1,
            "state": "ready",
        },
    )

    detail = service.get_task(job_id, "alice")

    assert detail["expiresAt"] == "2026-08-05T12:00:00Z"


def test_task_with_current_revision_publication_reopens_as_published(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    service = SkillWorkbenchService(tool_id="tool")
    payloads = {
        "request.json": {
            "jobId": job_id,
            "operation": "create",
            "intent": "Create actionable incident summaries",
            "revision": 2,
            "createdAt": 1,
            "publication": {
                "revision": 2,
                "skillId": "skill-1",
                "version": "3",
                "skillSpaceIds": ["space-1"],
                "disposition": "create-new",
                "region": "cn-beijing",
                "projectName": "default",
            },
        },
        "status.json": {"status": "succeeded", "stage": "packaging"},
    }
    monkeypatch.setattr(
        service,
        "_remote_json",
        lambda endpoint, requested_job_id, filename: payloads[filename],
    )

    detail = service._task_from_session("endpoint", job_id)

    assert detail["state"] == "published"
    assert service._task_summary(detail)["state"] == "published"


def _session(
    job_id: str,
    owner: str,
    endpoint: str,
    *,
    status: str = "Ready",
    expire_at: str = "2099-01-01T00:00:00Z",
    created_at: str = "2026-01-01T00:00:00Z",
) -> SimpleNamespace:
    return SimpleNamespace(
        session_id=f"session-{job_id}",
        user_session_id=job_id,
        endpoint=endpoint,
        status=status,
        expire_at=expire_at,
        created_at=created_at,
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


def test_publish_reuses_the_persisted_result_for_the_same_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    result = {
        "skillId": "skill-1",
        "version": "2",
        "skillSpaceIds": ["space-1"],
        "disposition": "create-new",
        "region": "cn-beijing",
        "projectName": "default",
    }
    monkeypatch.setattr(
        service,
        "get_task",
        lambda job_id, owner_id: {
            "jobId": job_id,
            "state": "published",
            "revision": 3,
            "source": None,
            "publication": {"revision": 3, **result},
        },
    )
    monkeypatch.setattr(
        service,
        "download",
        lambda *args, **kwargs: pytest.fail(
            "an idempotent retry must have no side effects"
        ),
    )

    actual = service.publish(
        service._new_job_id("alice"),
        "alice",
        PublishSkillTaskBody(
            disposition="create-new",
            expectedRevision=3,
            skillSpaceIds=["a-different-current-selection"],
        ),
    )

    assert actual == result


def test_publish_serializes_concurrent_requests_for_the_same_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    job_id = service._new_job_id("alice")
    body = PublishSkillTaskBody(
        disposition="create-new",
        expectedRevision=3,
        skillSpaceIds=["space-1"],
    )
    result = {
        "skillId": "skill-1",
        "version": "2",
        "skillSpaceIds": ["space-1"],
        "disposition": "create-new",
        "region": "cn-beijing",
        "projectName": "default",
    }
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()
    publication: dict[str, object] | None = None
    calls = 0
    side_effects = 0

    def publish_once(requested_job_id, owner_id, requested_body, report_progress):
        nonlocal calls, publication, side_effects
        assert requested_job_id == job_id
        assert owner_id == "alice"
        assert requested_body == body
        calls += 1
        if publication is None:
            first_entered.set()
            assert release_first.wait(timeout=2)
            side_effects += 1
            publication = result
        else:
            second_entered.set()
        return publication

    monkeypatch.setattr(service, "_publish_once", publish_once)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(service.publish, job_id, "alice", body)
        assert first_entered.wait(timeout=2)
        second = pool.submit(service.publish, job_id, "alice", body)
        assert not second_entered.wait(timeout=0.1)
        release_first.set()

        assert first.result(timeout=2) == result
        assert second.result(timeout=2) == result

    assert calls == 2
    assert side_effects == 1
    assert second_entered.is_set()


def test_publish_rejects_a_different_disposition_after_revision_is_published(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    monkeypatch.setattr(
        service,
        "get_task",
        lambda job_id, owner_id: {
            "jobId": job_id,
            "state": "published",
            "revision": 3,
            "source": {"kind": "skill-center", "skillId": "source-1"},
            "publication": {
                "revision": 3,
                "skillId": "source-1",
                "version": "4",
                "skillSpaceIds": ["space-1"],
                "disposition": "update-source",
                "region": "cn-beijing",
                "projectName": "default",
            },
        },
    )

    with pytest.raises(SkillWorkbenchError) as caught:
        service.publish(
            service._new_job_id("alice"),
            "alice",
            PublishSkillTaskBody(
                disposition="create-new",
                expectedRevision=3,
                skillSpaceIds=["space-1"],
            ),
        )

    assert caught.value.code == "SKILL_ALREADY_PUBLISHED"
    assert caught.value.status_code == 409


def test_persist_publication_writes_the_owner_bound_task_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    job_id = service._new_job_id("alice")
    uploaded: dict[str, object] = {}
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")
    monkeypatch.setattr(
        service,
        "_find_session",
        lambda tool_id, requested_job_id: {
            "endpoint": "https://devenv.example",
            "instanceId": "session-1",
        },
    )
    monkeypatch.setattr(
        service,
        "_remote_json",
        lambda endpoint, requested_job_id, filename: {
            "jobId": job_id,
            "operation": "create",
            "intent": "Create it",
            "revision": 2,
        },
    )

    def upload(endpoint, path, content, *, media_type="application/zip"):
        uploaded.update(
            endpoint=endpoint,
            path=path,
            body=json.loads(content),
            media_type=media_type,
        )

    monkeypatch.setattr(service, "_upload_file", upload)
    result = {
        "skillId": "skill-1",
        "version": "3",
        "skillSpaceIds": ["space-1"],
        "disposition": "create-new",
        "region": "cn-beijing",
        "projectName": "default",
    }

    service._persist_publication(job_id, "alice", 2, result)

    assert uploaded["endpoint"] == "https://devenv.example"
    assert uploaded["path"] == f"{service._remote_dir(job_id)}/request.json"
    assert uploaded["media_type"] == "application/json"
    uploaded_body = uploaded["body"]
    assert isinstance(uploaded_body, dict)
    assert uploaded_body["publication"] == {"revision": 2, **result}


def test_upload_route_accepts_a_valid_skill_zip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    service = mount_skill_workbench_routes(
        app,
        lambda request: "alice",
        lambda request: "Alice",
    )
    captured: dict[str, object] = {}

    def create_task(body, owner_id, creator_name, *, uploaded_archive=None):
        captured.update(
            body=body,
            owner_id=owner_id,
            creator_name=creator_name,
            uploaded_archive=uploaded_archive,
        )
        return {
            "jobId": SkillWorkbenchService._new_job_id(owner_id),
            "operation": body.operation,
            "intent": body.intent,
            "revision": 1,
            "state": "running",
            "stage": "generating",
            "activities": [],
            "files": [],
        }

    monkeypatch.setattr(service, "create_task", create_task)
    archive = skill_zip(extra={"references/checklist.md": "# Checklist\n"})

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/web/skill-workbench/tasks/from-upload",
            params={"intent": "Improve error guidance"},
            content=archive,
            headers={"content-type": "application/zip"},
        )

    assert response.status_code == 200
    assert captured["owner_id"] == "alice"
    assert captured["creator_name"] == "Alice"
    assert captured["uploaded_archive"] == archive
    body = captured["body"]
    assert isinstance(body, CreateSkillTaskBody)
    assert body.operation == "optimize"
    assert body.source is None


def test_upload_route_accepts_archive_at_size_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    service = mount_skill_workbench_routes(
        app,
        lambda request: "alice",
        lambda request: "Alice",
    )
    content = b"x" * (20 * 1024 * 1024)
    captured: dict[str, object] = {}

    def create_task(body, owner_id, creator_name, *, uploaded_archive=None):
        captured["uploaded_archive"] = uploaded_archive
        return {
            "jobId": SkillWorkbenchService._new_job_id(owner_id),
            "operation": body.operation,
            "intent": body.intent,
            "revision": 1,
            "state": "running",
            "stage": "generating",
            "activities": [],
            "files": [],
        }

    monkeypatch.setattr(service, "create_task", create_task)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/web/skill-workbench/tasks/from-upload",
            params={"intent": "Improve error guidance"},
            content=content,
            headers={"content-type": "application/zip"},
        )

    assert response.status_code == 200
    assert captured["uploaded_archive"] == content


@pytest.mark.parametrize(
    ("intent", "content", "status_code", "error_code"),
    [
        (" ", b"not-a-zip", 422, "SKILL_INTENT_REQUIRED"),
        (
            "Improve error guidance",
            b"x" * (20 * 1024 * 1024 + 1),
            413,
            "SKILL_ARCHIVE_TOO_LARGE",
        ),
    ],
    ids=["blank-intent", "oversized-archive"],
)
def test_upload_route_rejects_invalid_input_before_starting_a_task(
    monkeypatch: pytest.MonkeyPatch,
    intent: str,
    content: bytes,
    status_code: int,
    error_code: str,
) -> None:
    app = FastAPI()
    service = mount_skill_workbench_routes(
        app,
        lambda request: "alice",
        lambda request: "Alice",
    )
    monkeypatch.setattr(
        service,
        "create_task",
        lambda *args, **kwargs: pytest.fail("invalid uploads must not start a task"),
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/web/skill-workbench/tasks/from-upload",
            params={"intent": intent},
            content=content,
            headers={"content-type": "application/zip"},
        )

    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == error_code


def test_upload_route_rejects_chunked_content_above_size_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    service = mount_skill_workbench_routes(
        app,
        lambda request: "alice",
        lambda request: "Alice",
    )
    monkeypatch.setattr(
        service,
        "create_task",
        lambda *args, **kwargs: pytest.fail("oversized uploads must not start a task"),
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/web/skill-workbench/tasks/from-upload",
            params={"intent": "Improve error guidance"},
            content=iter([b"x" * (20 * 1024 * 1024), b"x"]),
            headers={"content-type": "application/zip"},
        )

    assert response.status_code == 413
    assert response.json()["detail"] == {
        "code": "SKILL_ARCHIVE_TOO_LARGE",
        "message": "Skill ZIP 不能超过 20 MiB",
        "retryable": False,
    }


def test_artifact_returns_every_validated_nested_text_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    content = skill_zip(
        extra={
            "references/checklist.md": "# Checklist\n",
            "scripts/render.py": "print('ready')\n",
        },
        member_prefix="./",
    )
    monkeypatch.setattr(
        service,
        "_download_archive",
        lambda job_id, owner_id: validate_skill_archive(content),
    )

    artifact = service.artifact(
        SkillWorkbenchService._new_job_id("alice"),
        "alice",
    )

    assert artifact == {
        "name": "release-notes",
        "description": "Create concise release notes.",
        "files": [
            {
                "path": "SKILL.md",
                "size": len(
                    (
                        "---\n"
                        "name: release-notes\n"
                        "description: Create concise release notes.\n"
                        "---\n\n"
                        "# Instructions\n"
                    ).encode("utf-8")
                ),
                "content": (
                    "---\n"
                    "name: release-notes\n"
                    "description: Create concise release notes.\n"
                    "---\n\n"
                    "# Instructions\n"
                ),
            },
            {
                "path": "references/checklist.md",
                "size": len("# Checklist\n".encode("utf-8")),
                "content": "# Checklist\n",
            },
            {
                "path": "scripts/render.py",
                "size": len("print('ready')\n".encode("utf-8")),
                "content": "print('ready')\n",
            },
        ],
    }


def test_publish_stream_reports_progress_and_destination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    service = mount_skill_workbench_routes(
        app,
        lambda request: "alice",
        lambda request: "Alice",
    )
    job_id = SkillWorkbenchService._new_job_id("alice")

    def publish(requested_job_id, owner_id, body, report_progress=None):
        assert requested_job_id == job_id
        assert owner_id == "alice"
        assert body.region == "cn-shanghai"
        assert report_progress is not None
        report_progress(
            {
                "phase": "uploading",
                "message": "正在上传 Skill 包",
            }
        )
        report_progress(
            {
                "phase": "activating",
                "message": "正在等待版本生效",
            }
        )
        return {
            "skillId": "skill-1",
            "version": "2",
            "skillSpaceIds": ["space-1"],
            "disposition": "create-new",
            "region": "cn-shanghai",
            "projectName": "default",
        }

    monkeypatch.setattr(service, "publish", publish)

    with TestClient(app) as client:
        response = client.post(
            f"/web/skill-workbench/tasks/{job_id}/publish-stream",
            json={
                "disposition": "create-new",
                "skillSpaceIds": ["space-1"],
                "projectName": "default",
                "region": "cn-shanghai",
                "expectedRevision": 1,
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in response.text.splitlines() if line]
    assert events == [
        {
            "type": "progress",
            "phase": "uploading",
            "message": "正在上传 Skill 包",
        },
        {
            "type": "progress",
            "phase": "activating",
            "message": "正在等待版本生效",
        },
        {
            "type": "complete",
            "result": {
                "skillId": "skill-1",
                "version": "2",
                "skillSpaceIds": ["space-1"],
                "disposition": "create-new",
                "region": "cn-shanghai",
                "projectName": "default",
            },
        },
    ]
