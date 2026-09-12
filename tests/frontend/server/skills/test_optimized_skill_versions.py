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

import io
import time
import zipfile
from types import SimpleNamespace
from typing import Any

import pytest

from frontend.server.skills import storage
from frontend.server.skills.archive import validate_skill_archive
from frontend.server.skills.devenv import PublishSkillTaskBody, SkillWorkbenchService
from frontend.server.skills.repository import SkillRepositoryError


class OptimizedSkillClient:
    def __init__(self, new_status: str = "running") -> None:
        self.version_reads: list[bool] = []
        self.updated = False
        self.show_new = False
        self.new_status = new_status
        self.published: list[Any] = []

    def list_skill_spaces_by_skill(self, _: Any) -> Any:
        return SimpleNamespace(items=[], total_count=0)

    def get_skill_space(self, _: Any) -> Any:
        return SimpleNamespace(name="personal", description="")

    def list_skill_versions(self, _: Any) -> Any:
        self.version_reads.append(self.updated)
        items = [SimpleNamespace(version="v1", status="running", error_message="")]
        if self.show_new:
            items.append(
                SimpleNamespace(
                    version="v2",
                    status=self.new_status,
                    error_message="New version failed",
                )
            )
        return SimpleNamespace(items=items, total_count=len(items))

    def update_skill(self, request: Any) -> None:
        assert request.id == "original-skill"
        self.updated = True

    def publish_skill_to_skill_space(self, request: Any) -> None:
        self.published.append(request)


@pytest.fixture
def setup(monkeypatch: pytest.MonkeyPatch):
    cloud = OptimizedSkillClient()
    service = SkillWorkbenchService(
        region="cn-beijing", skills_client_factory=lambda _: cloud
    )
    source_task = {
        "revision": 1,
        "state": "ready",
        "source": {"skillId": "original-skill", "region": "cn-beijing"},
    }
    monkeypatch.setattr(service, "_get_task_with_session", lambda *_: (source_task, {}))
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(
            "summary/SKILL.md",
            "---\nname: summary\ndescription: Updated\n---\nUpdated instructions",
        )
    content = validate_skill_archive(archive.getvalue())
    monkeypatch.setattr(
        service, "_download_archive_from_session", lambda *_args, **_kwargs: content
    )
    publications = []
    monkeypatch.setattr(
        service,
        "_persist_publication",
        lambda *_args, **_kwargs: publications.append(_args[3]),
    )
    config = SimpleNamespace(tos=SimpleNamespace(bucket="", prefix=""))
    monkeypatch.setattr(
        "agentkit.toolkit.config.GlobalConfigManager.load", lambda _: config
    )
    monkeypatch.setattr(
        storage,
        "resolve_skill_publish_storage",
        lambda **_: SimpleNamespace(provider="volcengine", bucket="bucket"),
    )
    monkeypatch.setattr(
        storage, "resolve_skill_publish_credentials", lambda **_: object()
    )
    monkeypatch.setattr(storage, "ensure_skill_publish_bucket", lambda *_: None)
    monkeypatch.setattr(
        storage, "upload_skill_archive", lambda *_: "tos://bucket/updated.zip"
    )
    return service, cloud, publications


def test_optimized_skill_waits_through_old_version_readback_before_publishing(
    setup, monkeypatch
):
    service, cloud, publications = setup
    waited = []
    global_sleep = time.sleep

    def reveal_new(_: float):
        waited.append(True)
        cloud.show_new = True

    monkeypatch.setattr("frontend.server.skills.versions.sleep", reveal_new)
    assert time.sleep is global_sleep
    result = service.publish(
        "job",
        "alice",
        PublishSkillTaskBody(
            disposition="update-source", skillSpaceIds=["personal"], expectedRevision=1
        ),
    )
    assert cloud.version_reads == [False, True, True]
    assert waited == [True]
    assert result["skillId"] == "original-skill"
    assert result["version"] == "v2"
    assert cloud.published[0].skills[0].version == "v2"
    assert publications[0]["version"] == "v2"


def test_failed_optimized_version_does_not_republish_old_successful_version(
    setup, monkeypatch
):
    service, cloud, publications = setup
    cloud.new_status = "failed"
    monkeypatch.setattr(
        "frontend.server.skills.versions.sleep",
        lambda _: setattr(cloud, "show_new", True),
    )
    with pytest.raises(SkillRepositoryError) as error:
        service._publish_once(
            "job",
            "alice",
            PublishSkillTaskBody(
                disposition="update-source",
                skillSpaceIds=["personal"],
                expectedRevision=1,
            ),
        )
    assert error.value.code == "SKILL_VERSION_FAILED"
    assert cloud.published == []
    assert publications == []
