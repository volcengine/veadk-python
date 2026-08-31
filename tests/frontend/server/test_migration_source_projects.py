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
import zipfile
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest

from frontend.server.intelligent_development import DeliveryReference
from frontend.server.intelligent_development_projects import (
    IntelligentDevelopmentProjectService,
    TosIntelligentDevelopmentProjectRepository,
)
from frontend.server.intelligent_development_source import (
    load_intelligent_development_artifact,
    materialize_intelligent_development_preview,
)
from frontend.server.intelligent_development_task import IntentDecision
from frontend.server.sandbox_remote import SandboxRemoteTransport


class _TosError(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"TOS {status_code}")


class _FakeTos:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, *, key, content, forbid_overwrite=False, **_kwargs):
        if forbid_overwrite and key in self.objects:
            raise _TosError(409)
        self.objects[key] = bytes(content)

    def get_object(self, *, key, **_kwargs):
        if key not in self.objects:
            raise _TosError(404)
        return io.BytesIO(self.objects[key])

    def delete_object(self, *, key, **_kwargs):
        self.objects.pop(key, None)

    def list_objects_type2(self, *, prefix, **_kwargs):
        return SimpleNamespace(
            contents=[
                SimpleNamespace(key=key)
                for key in sorted(self.objects)
                if key.startswith(prefix)
            ],
            is_truncated=False,
            next_continuation_token="",
        )


def _migration_artifact() -> tuple[bytes, list[dict[str, object]]]:
    files = {
        "app.py": b"agent = object()\n",
        "migration-report.md": b"# Migration\n\nVerified.\n",
    }
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
        for path, content in files.items():
            package.writestr(path, content)
    descriptors = [
        {
            "path": path,
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "mode": "0644",
        }
        for path, content in files.items()
    ]
    return archive.getvalue(), descriptors


@pytest.mark.asyncio
async def test_migration_version_is_idempotent_filterable_and_reusable(
    tmp_path,
) -> None:
    tos = _FakeTos()
    service = IntelligentDevelopmentProjectService(
        TosIntelligentDevelopmentProjectRepository(
            bucket="studio",
            client_factory=lambda: tos,
        )
    )
    artifact, files = _migration_artifact()
    task_id = "migration-v1-" + "1" * 32
    result: dict[str, object] = {
        "schema_version": 1,
        "run_id": task_id,
        "cli": {"name": "agentkit-cli", "version": "0.52.1"},
        "migration": {
            "engine": "agentic",
            "framework": "any",
            "source_sha256": "2" * 64,
            "provenance_sha256": "3" * 64,
        },
        "status": "succeeded",
        "files": files,
        "startup": {"module": "app.py", "object": "agent"},
        "environment": {"required": ["MODEL_API_KEY"], "optional": ["TZ"]},
        "verification": {
            "status": "passed",
            "checks": [{"name": "import", "status": "passed"}],
        },
        "warnings": [],
        "report": {"path": "migration-report.md"},
        "artifact": {
            "path": "migration-result.zip",
            "size": len(artifact),
            "sha256": hashlib.sha256(artifact).hexdigest(),
        },
        "created_at": "2026-08-27T08:00:00Z",
    }
    report = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()

    first_project, first_version = await service.persist_migration(
        owner_id="owner",
        task_id=task_id,
        project_name="travel-agent",
        artifact=artifact,
        result=result,
        result_bytes=report,
        environment_defaults={"TZ": "Asia/Shanghai"},
    )
    repeated_project, repeated_version = await service.persist_migration(
        owner_id="owner",
        task_id=task_id,
        project_name="travel-agent",
        artifact=artifact,
        result=result,
        result_bytes=report,
        environment_defaults={"TZ": "Asia/Shanghai"},
    )

    assert first_project.origin == "migration"
    assert repeated_project.version_count == 1
    assert repeated_version.version_id == first_version.version_id
    assert repeated_version.producer == "migration"
    assert repeated_version.environment.defaults == {"TZ": "Asia/Shanghai"}
    assert await service.list_projects("owner", origin="intelligent-development") == []
    assert [
        project.project_id
        for project in await service.list_projects("owner", origin="migration")
    ] == [first_project.project_id]

    source = {
        "kind": "intelligentDevelopment",
        "sessionId": task_id,
        "projectId": first_project.project_id,
        "versionId": first_version.version_id,
        "artifactSha256": first_version.artifact_sha256,
        "validationReportSha256": first_version.validation_report_sha256,
    }
    preview = await materialize_intelligent_development_preview(
        tmp_path / "preview",
        source,
        owner_id="owner",
        service=None,
        project_service=service,
    )
    loaded = await load_intelligent_development_artifact(
        tmp_path / "download",
        source,
        owner_id="owner",
        service=None,
        project_service=service,
    )

    assert preview.entry_point == "app.py"
    assert preview.environment_required == ("MODEL_API_KEY",)
    assert preview.environment_defaults == (("TZ", "Asia/Shanghai"),)
    assert {item.path for item in preview.files} == {"app.py", "migration-report.md"}
    assert loaded.content == artifact

    binding = await service.create_binding(
        owner_id="owner",
        session_id="intelligent-session",
        display_name="ignored for an existing project",
        project_id=first_project.project_id,
        base_version_id=first_version.version_id,
    )
    base = await service.base_version("owner", binding.session_id)
    assert base is not None
    assert base.artifact == artifact

    next_artifact = b"next intelligent-development source"
    next_report = json.dumps(
        {"acceptanceCriteria": ["保留迁移能力并完成优化"]},
        ensure_ascii=False,
    ).encode()
    delivery = DeliveryReference(
        artifact_sha256=hashlib.sha256(next_artifact).hexdigest(),
        artifact_size=len(next_artifact),
        validation_report_sha256=hashlib.sha256(next_report).hexdigest(),
        session_id=binding.session_id,
        agent_name="travel_agent_v2",
        entry_point="app.py",
        file_count=1,
        validated_at="2026-08-27T09:00:00Z",
        gate_summary=("local-checks",),
        deployable=True,
        verified=True,
        validation_summary="验证通过",
    )
    transport = cast(
        SandboxRemoteTransport,
        SimpleNamespace(download=AsyncMock(side_effect=[next_artifact, next_report])),
    )
    next_project, next_version = await service.persist_delivery(
        owner_id="owner",
        session_id=binding.session_id,
        transport=transport,
        delivery=delivery,
        decision=IntentDecision(
            decision="accept",
            message="",
            intent_summary="优化旅游规划能力",
            acceptance_criteria=("保留迁移能力并完成优化",),
            changes_delivery=True,
        ),
    )

    assert next_project.origin == "migration"
    assert next_project.version_count == 2
    assert next_version.parent_version_id == first_version.version_id
    assert next_version.producer == "intelligent-development"
    assert next_version.migration_framework == "any"
    assert next_version.migration_engine == "agentic"
    assert [
        version.version_id
        for version in await service.list_versions("owner", first_project.project_id)
    ] == [next_version.version_id, first_version.version_id]
    assert await service.list_projects("owner", origin="intelligent-development") == []
