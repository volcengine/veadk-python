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

import base64
import io
import json
import stat
import zipfile
from types import SimpleNamespace

import pytest

from frontend.server.skills.archive import SkillArchiveError, validate_skill_archive
from frontend.server.skills.devenv import (
    CreateSkillTaskBody,
    SkillWorkbenchError,
    SkillWorkbenchService,
)
from frontend.server.skills.models import (
    CreateSkillSpaceBody,
    SkillIdentity,
    UpdateSkillSpaceBody,
)
from frontend.server.skills.prompts import decorate_intent
from frontend.server.skills.repository import AgentKitSkillRepository
from frontend.server.skills.routes import _convert_error
from frontend.server.skills.service import SkillService
from veadk.cli.frontend_skill_creator import _sandbox_model_config

SKILL_MD = """---
name: example-skill
description: A focused test Skill
---

# Example
"""


def archive(files: dict[str, bytes], *, symlink: str | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as target:
        for path, content in files.items():
            target.writestr(path, content)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            target.writestr(info, b"SKILL.md")
    return buffer.getvalue()


@pytest.mark.parametrize(
    "files",
    [
        {"SKILL.md": SKILL_MD.encode(), "references/example.png": b"\x89PNG"},
        {"wrapper/SKILL.md": SKILL_MD.encode(), "wrapper/references/notes.txt": b"ok"},
    ],
)
def test_skill_archive_accepts_root_or_one_wrapper(files: dict[str, bytes]) -> None:
    result = validate_skill_archive(archive(files))

    assert result.name == "example-skill"
    assert result.description == "A focused test Skill"
    assert result.files[0]["path"] == "SKILL.md"


@pytest.mark.parametrize(
    ("indicator", "expected"),
    [
        (">", "Create focused Skills from clear requirements.\n"),
        (">-", "Create focused Skills from clear requirements."),
        ("|", "Create focused Skills\nfrom clear requirements.\n"),
        ("|-", "Create focused Skills\nfrom clear requirements."),
    ],
)
def test_skill_archive_parses_yaml_block_descriptions(
    indicator: str,
    expected: str,
) -> None:
    skill_md = f"""---
name: yaml-description
description: {indicator}
  Create focused Skills
  from clear requirements.
---

# YAML description
"""

    result = validate_skill_archive(archive({"SKILL.md": skill_md.encode()}))

    assert result.description == expected


@pytest.mark.parametrize(
    ("content", "code", "message"),
    [
        (
            archive({"nested/two/file.txt": b"x"}),
            "SKILL_MD_NOT_AT_ROOT",
            "根目录必须包含 SKILL.md",
        ),
        (
            archive({"SKILL.md": b"name: broken"}),
            "SKILL_MD_FRONTMATTER_MISSING",
            "第 1 行必须",
        ),
        (
            archive({"../SKILL.md": SKILL_MD.encode()}),
            "SKILL_ARCHIVE_UNSAFE_PATH",
            "../SKILL.md",
        ),
        (
            archive({"SKILL.md": SKILL_MD.encode()}, symlink="link"),
            "SKILL_ARCHIVE_SYMLINK",
            "link",
        ),
    ],
)
def test_skill_archive_returns_stable_detailed_errors(
    content: bytes,
    code: str,
    message: str,
) -> None:
    with pytest.raises(SkillArchiveError) as raised:
        validate_skill_archive(content)

    assert raised.value.code == code
    assert message in str(raised.value)


def test_unexpected_skill_service_error_preserves_original_error() -> None:
    converted = _convert_error(
        RuntimeError("Volcengine credentials not found: missing access key")
    )

    assert converted.status_code == 502
    assert converted.detail == {
        "code": "SKILL_SERVICE_UNAVAILABLE",
        "message": "暂时无法访问 AgentKit Skills。",
        "retryable": True,
        "originalError": {
            "type": "builtins.RuntimeError",
            "message": "Volcengine credentials not found: missing access key",
            "repr": "RuntimeError('Volcengine credentials not found: missing access key')",
        },
    }


def test_skill_workbench_error_preserves_original_error() -> None:
    error = SkillWorkbenchError(
        "SKILL_WORKBENCH_INTERNAL",
        "技能生成服务异常。",
        status_code=500,
        original_error=RuntimeError("sandbox session failed to start"),
    )

    assert error.detail()["originalError"] == {
        "type": "builtins.RuntimeError",
        "message": "sandbox session failed to start",
        "repr": "RuntimeError('sandbox session failed to start')",
    }


class FakeRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def list_spaces(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("list", kwargs))
        return {"items": []}

    def create_space(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("create", kwargs))
        return {"id": "space-1"}

    def update_space(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("update", kwargs))
        return {"id": "space-1", "name": kwargs["name"]}

    def delete_space(self, **kwargs: object) -> None:
        self.calls.append(("delete", kwargs))


def test_regular_users_filter_spaces_by_author_but_admins_see_all() -> None:
    repository = FakeRepository()
    service = SkillService(repository)  # type: ignore[arg-type]

    service.list_spaces(
        SkillIdentity(author="person@example.com"),
        region="cn-beijing",
        page=1,
        page_size=20,
        project_name=None,
    )
    service.list_spaces(
        SkillIdentity(author="admin@example.com", is_admin=True),
        region="cn-beijing",
        page=1,
        page_size=20,
        project_name=None,
    )

    assert repository.calls[0][1]["author"] == "person@example.com"
    assert repository.calls[1][1]["author"] is None


def test_space_creation_always_adds_resolved_author() -> None:
    repository = FakeRepository()
    service = SkillService(repository)  # type: ignore[arg-type]

    service.create_space(
        SkillIdentity(author="local-user"),
        CreateSkillSpaceBody(
            name="Shared skills", description="Team utilities", region="cn-beijing"
        ),
    )

    assert repository.calls[0][0] == "create"
    assert repository.calls[0][1]["author"] == "local-user"


def test_repository_sends_author_tag_filter_and_maps_response_tag() -> None:
    requests: list[object] = []

    class Client:
        def list_skill_spaces(self, request: object) -> SimpleNamespace:
            requests.append(request)
            return SimpleNamespace(
                total_count=1,
                items=[
                    SimpleNamespace(
                        id="space-1",
                        name="Personal skills",
                        description="",
                        status="Ready",
                        project_name="default",
                        update_time_stamp="",
                        relations=[],
                        tags=[
                            SimpleNamespace(key="author", value="person@example.com")
                        ],
                    )
                ],
            )

    repository = AgentKitSkillRepository(lambda region: Client())
    result = repository.list_spaces(
        region="cn-beijing",
        page=1,
        page_size=20,
        project_name=None,
        author="person@example.com",
    )

    request = requests[0]
    assert request.tag_filters[0].key == "author"
    assert request.tag_filters[0].values == ["person@example.com"]
    assert result["items"][0]["author"] == "person@example.com"


def test_repository_adds_author_tag_when_creating_space() -> None:
    requests: list[object] = []

    class Client:
        def create_skill_space(self, request: object) -> SimpleNamespace:
            requests.append(request)
            return SimpleNamespace(id="space-1")

    repository = AgentKitSkillRepository(lambda region: Client())
    result = repository.create_space(
        region="cn-beijing",
        name="Personal skills",
        description=None,
        project_name="default",
        author="person@example.com",
    )

    request = requests[0]
    assert request.tags[0].key == "author"
    assert request.tags[0].value == "person@example.com"
    assert result["author"] == "person@example.com"


def test_space_update_and_delete_use_the_selected_region() -> None:
    repository = FakeRepository()
    service = SkillService(repository)  # type: ignore[arg-type]
    identity = SkillIdentity(author="local-user")

    updated = service.update_space(
        identity,
        "space-1",
        UpdateSkillSpaceBody(
            name="Renamed space",
            description="Updated description",
            region="cn-beijing",
        ),
    )
    service.delete_space(identity, region="cn-beijing", space_id="space-1")

    assert updated["name"] == "Renamed space"
    assert repository.calls[0] == (
        "update",
        {
            "region": "cn-beijing",
            "space_id": "space-1",
            "name": "Renamed space",
            "description": "Updated description",
        },
    )
    assert repository.calls[1] == (
        "delete",
        {"region": "cn-beijing", "space_id": "space-1"},
    )


def test_workbench_reports_admin_not_configured_without_a_tool() -> None:
    capability = SkillWorkbenchService(tool_id="", region="cn-beijing").capabilities()

    assert capability["enabled"] is False
    assert capability["reason"] == "管理员未配置"


def test_prompt_injects_preset_or_custom_style_and_optional_name() -> None:
    preset = decorate_intent(
        "Create a review skill", style="strict", name="review-skill"
    )
    custom = decorate_intent(
        "Create a review skill", style="Use short examples", name=None
    )

    assert "review-skill" in preset
    assert "robust constraints" in preset
    assert "Use short examples" in custom


class FakeResponse:
    status_code = 200

    def json(self) -> dict[str, object]:
        return {"data": {"status": "running"}}


class FakeToolsClient:
    def __init__(self, tool: SimpleNamespace) -> None:
        self.tool = tool
        self.created: list[object] = []

    def get_tool(self, request: object) -> SimpleNamespace:
        del request
        return self.tool

    def create_session(self, request: object) -> SimpleNamespace:
        self.created.append(request)
        return SimpleNamespace(
            session_id="session-1",
            endpoint="https://sandbox.invalid",
            expire_at="2026-08-07T10:00:00Z",
        )


def test_workbench_accepts_custom_model_and_injects_it_per_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, base_url = _sandbox_model_config("volcengine")
    tool = SimpleNamespace(
        tool_type="DevEnv",
        status="Ready",
        image_url="",
        envs=[
            SimpleNamespace(key="CODEX_MODEL", value="model-a"),
            SimpleNamespace(key="CODEX_API_KEY", value="secret"),
            SimpleNamespace(key="CODEX_BASE_URL", value=base_url),
        ],
    )
    client = FakeToolsClient(tool)
    launches: list[dict[str, object]] = []

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        del url
        launches.append(kwargs)
        return FakeResponse()

    monkeypatch.setenv("VEADK_SKILL_MODELS", "model-a,model-b")
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "volcengine")
    monkeypatch.setattr("frontend.server.skills.devenv.requests.post", fake_post)
    service = SkillWorkbenchService(
        tool_id="tool-1",
        region="cn-beijing",
        tools_client_factory=lambda region: client,
    )

    with pytest.raises(ValueError, match="模型 ID"):
        CreateSkillTaskBody(
            operation="create",
            intent="Build a Skill",
            model="invalid model",
        )

    result = service.create_task(
        CreateSkillTaskBody(
            operation="create",
            intent="Build a Skill",
            model="custom-model",
            style="tutorial",
            name="demo-skill",
        ),
        "owner-1",
        "Owner",
    )

    assert result["model"] == "custom-model"
    session_envs = {item.key: item.value for item in client.created[0].envs}
    assert session_envs["CODEX_MODEL"] == "custom-model"
    assert "CODEX_API_KEY" not in session_envs
    launch_env = launches[0]["json"]["env"]  # type: ignore[index]
    prompt = base64.b64decode(launch_env["VEADK_SKILL_PROMPT_B64"]).decode()  # type: ignore[index]
    assert "demo-skill" in prompt
    assert "tutorial-friendly" in prompt
    assert "directly under `<frontmatter-name>/`" in prompt
    assert "Do not create `result.json`" in prompt
    assert "a `.veadk-output` directory" in prompt


def test_workbench_byteplus_uses_default_and_catalog_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, base_url = _sandbox_model_config("byteplus")
    catalog = {
        "models": [
            {
                "slug": "default-model",
                "display_name": "Default model",
                "visibility": "list",
                "supported_in_api": True,
            },
            {
                "slug": "optional-model",
                "display_name": "Optional model",
                "visibility": "list",
                "supported_in_api": True,
            },
            {
                "slug": "hidden-model",
                "visibility": "hidden",
                "supported_in_api": True,
            },
            {
                "slug": "unsupported-model",
                "visibility": "list",
                "supported_in_api": False,
            },
            {
                "slug": "doubao-seed-2-0-pro-260215",
                "display_name": "Volcengine-only model",
                "visibility": "list",
                "supported_in_api": True,
            },
        ]
    }
    tool = SimpleNamespace(
        tool_type="DevEnv",
        status="Ready",
        image_url="",
        envs=[
            SimpleNamespace(key="CODEX_MODEL", value="default-model"),
            SimpleNamespace(key="CODEX_API_KEY", value="secret"),
            SimpleNamespace(key="CODEX_BASE_URL", value=base_url),
            SimpleNamespace(
                key="CODEX_MODEL_CATALOG_JSON",
                value=json.dumps(catalog),
            ),
        ],
    )
    client = FakeToolsClient(tool)
    regions: list[str] = []

    def client_for_region(region: str) -> FakeToolsClient:
        regions.append(region)
        return client

    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv(
        "VEADK_SKILL_MODELS",
        "optional-model,admin-model,admin-model",
    )
    monkeypatch.setattr(
        "frontend.server.skills.devenv.requests.post",
        lambda *args, **kwargs: FakeResponse(),
    )
    service = SkillWorkbenchService(
        tool_id="tool-1",
        region="cn-beijing",
        tools_client_factory=client_for_region,
    )

    capability = service.capabilities()

    assert regions == ["ap-southeast-1"]
    assert capability["enabled"] is True
    assert capability["models"] == [
        {"id": "seed-2-0-lite-260228", "label": "seed-2-0-lite-260228"},
        {"id": "default-model", "label": "default-model"},
        {"id": "optional-model", "label": "Optional model"},
        {"id": "admin-model", "label": "admin-model"},
    ]

    result = service.create_task(
        CreateSkillTaskBody(
            operation="create",
            intent="Build a BytePlus Skill",
            model="optional-model",
        ),
        "owner-1",
        "Owner",
    )

    assert result["model"] == "optional-model"
    session_envs = {item.key: item.value for item in client.created[0].envs}
    assert session_envs["CODEX_MODEL"] == "optional-model"
