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

import asyncio
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.testclient import TestClient

from veadk.cli.cli_frontend import _run_frontend_server
from veadk.cli.frontend_skill_creator import _sandbox_model_config


def _create_frontend_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    provider: str = "volcengine",
    admins: str | None = None,
    developers: str | None = None,
) -> FastAPI:
    captured: dict[str, Any] = {}
    monkeypatch.setattr("dotenv.find_dotenv", lambda *args, **kwargs: "")
    monkeypatch.setattr(
        "uvicorn.run",
        lambda app, **kwargs: captured.setdefault("app", app),
    )
    if provider == "byteplus":
        monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "ak")
        monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "sk")
    else:
        monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "ak")
        monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "sk")

    _run_frontend_server(
        agents_dir=str(tmp_path),
        frontend_dir=None,
        site_logo=None,
        site_title=None,
        host="127.0.0.1",
        port=8765,
        dev=True,
        vite=True,
        oauth2_user_pool=None,
        oauth2_user_pool_client=None,
        oauth2_user_pool_uid=None,
        oauth2_user_pool_client_uid=None,
        oauth2_redirect_uri=None,
        oauth2_provider=None,
        oauth2_provider_label=None,
        auth_mode="frontend",
        generated_agent_test_run_ttl=60,
        studio_admins=admins,
        studio_developers=developers,
        open_browser=False,
        provider=provider,
    )
    return captured["app"]


def _assert_sdk_call_is_off_event_loop() -> None:
    with pytest.raises(RuntimeError, match="no running event loop"):
        asyncio.get_running_loop()


@pytest.mark.parametrize(
    "provider,expected_encoding",
    [("volcengine", "gzip"), ("byteplus", None)],
)
def test_frontend_server_uses_provider_compatible_static_response_encoding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider: str,
    expected_encoding: str | None,
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path, provider=provider)

    @app.get("/compression-probe")
    def compression_probe() -> Response:
        return Response(".library-card{}" * 4096, media_type="text/css")

    response = TestClient(app).get(
        "/compression-probe",
        headers={"Accept-Encoding": "gzip"},
    )

    assert response.status_code == 200
    assert response.headers.get("content-encoding") == expected_encoding
    if expected_encoding:
        assert "Accept-Encoding" in response.headers["vary"]


def test_list_a2a_spaces_paginates_and_maps_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path, developers="developer")
    calls: list[dict[str, Any]] = []

    class _FakeResponse:
        def __init__(self, payload: dict[str, Any]) -> None:
            self.status_code = 200
            self._payload = payload

        def json(self) -> dict[str, Any]:
            return self._payload

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            del args

        async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
            body = json.loads(kwargs["content"].decode("utf-8"))
            calls.append(
                {
                    "url": url,
                    "params": kwargs["params"],
                    "headers": kwargs["headers"],
                    "body": body,
                }
            )
            page = body["PageNumber"]
            items = [
                {
                    "Id": "as-1",
                    "Name": "默认智能体中心",
                    "IntentEnabled": True,
                    "ProjectName": "default",
                    "Tags": [{"Key": "env", "Value": "prod"}],
                    "IsDefault": True,
                },
                {
                    "Id": "as-2",
                    "Name": "客服智能体中心",
                    "IntentEnabled": False,
                    "ProjectName": "default",
                    "Tags": [],
                    "IsDefault": False,
                },
            ]
            if page == 2:
                items = [
                    {
                        "Id": "as-3",
                        "Name": "销售智能体中心",
                        "IntentEnabled": True,
                        "ProjectName": "default",
                        "Tags": [],
                        "IsDefault": False,
                    }
                ]
            return _FakeResponse({"Result": {"TotalCount": 3, "Items": items}})

    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    with TestClient(app) as client:
        response = client.get(
            "/web/a2a-spaces",
            params={"region": "cn-beijing", "page_size": 2, "project": "default"},
            headers={"X-VeADK-Local-User": "developer"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": "as-1",
                "name": "默认智能体中心",
                "intentEnabled": True,
                "projectName": "default",
                "tags": [{"key": "env", "value": "prod"}],
                "isDefault": True,
                "region": "cn-beijing",
            },
            {
                "id": "as-2",
                "name": "客服智能体中心",
                "intentEnabled": False,
                "projectName": "default",
                "tags": [],
                "isDefault": False,
                "region": "cn-beijing",
            },
            {
                "id": "as-3",
                "name": "销售智能体中心",
                "intentEnabled": True,
                "projectName": "default",
                "tags": [],
                "isDefault": False,
                "region": "cn-beijing",
            },
        ],
        "totalCount": 3,
        "page": 1,
        "pageSize": 2,
    }
    assert [call["body"]["PageNumber"] for call in calls] == [1, 2]
    assert all(call["body"]["PageSize"] == 2 for call in calls)
    assert all(call["body"]["ProjectName"] == "default" for call in calls)
    assert calls[0]["params"]["Action"] == "ListA2aSpaces"
    assert calls[0]["params"]["Version"] == "2025-10-30"
    assert calls[0]["url"] == "https://agentkit.cn-beijing.volcengineapi.com"
    assert "Authorization" in calls[0]["headers"]
    assert "X-Content-Sha256" in calls[0]["headers"]


def test_a2a_space_routes_keep_missing_credentials_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)
    monkeypatch.delenv("VOLCENGINE_ACCESS_KEY")
    monkeypatch.delenv("VOLCENGINE_SECRET_KEY")

    with TestClient(app) as client:
        response = client.get("/web/a2a-spaces", params={"region": "cn-beijing"})

    assert response.status_code == 409


def test_list_skill_spaces_maps_metadata_and_pagination(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)
    calls: list[tuple[str, Any]] = []

    class _FakeSkillsClient:
        def __init__(self, **kwargs: Any) -> None:
            self.region = kwargs["region"]

        def list_skill_spaces(self, request: Any) -> SimpleNamespace:
            _assert_sdk_call_is_off_event_loop()
            calls.append((self.region, request))
            return SimpleNamespace(
                total_count=23,
                items=[
                    SimpleNamespace(
                        id="space-1",
                        name="客户支持技能",
                        description="客服工作流",
                        status="Ready",
                        project_name="support-project",
                        update_time_stamp="2026-07-22T08:30:00Z",
                        relations=[SimpleNamespace(), SimpleNamespace()],
                    )
                ],
            )

    monkeypatch.setattr(
        "agentkit.sdk.skills.client.AgentkitSkillsClient", _FakeSkillsClient
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/skill-spaces",
            params={
                "region": "cn-shanghai",
                "page": 2,
                "page_size": 10,
                "project": "support-project",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": "space-1",
                "name": "客户支持技能",
                "description": "客服工作流",
                "status": "Ready",
                "region": "cn-shanghai",
                "projectName": "support-project",
                "updatedAt": "2026-07-22T08:30:00Z",
                "skillCount": 2,
            }
        ],
        "totalCount": 23,
        "page": 2,
        "pageSize": 10,
    }
    assert len(calls) == 1
    region, request = calls[0]
    assert region == "cn-shanghai"
    assert request.page_number == 2
    assert request.page_size == 10
    assert request.project_name == "support-project"


def test_list_skill_spaces_defaults_to_local_studio_region(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)
    calls: list[tuple[str, Any]] = []

    class _FakeSkillsClient:
        def __init__(self, **kwargs: Any) -> None:
            self.region = kwargs["region"]

        def list_skill_spaces(self, request: Any) -> SimpleNamespace:
            calls.append((self.region, request))
            return SimpleNamespace(
                total_count=100,
                items=[
                    SimpleNamespace(
                        id=f"space-{self.region}",
                        name=self.region,
                        description="",
                        status="Ready",
                        project_name="",
                        update_time_stamp="",
                        relations=[],
                    )
                ],
            )

    monkeypatch.setattr(
        "agentkit.sdk.skills.client.AgentkitSkillsClient", _FakeSkillsClient
    )

    with TestClient(app) as client:
        response = client.get("/web/skill-spaces")

    assert response.status_code == 200
    assert response.json()["totalCount"] == 100
    assert response.json()["page"] == 1
    assert response.json()["pageSize"] == 50
    assert {item["region"] for item in response.json()["items"]} == {"cn-beijing"}
    assert {region for region, _ in calls} == {"cn-beijing"}
    assert all(request.page_number == 1 for _, request in calls)
    assert all(request.page_size == 50 for _, request in calls)
    assert all(request.project_name is None for _, request in calls)


@pytest.mark.parametrize(
    ("provider", "region", "expected_host"),
    [
        ("volcengine", "cn-beijing", "open.volcengineapi.com"),
        (
            "byteplus",
            "ap-southeast-1",
            "agentkit.ap-southeast-1.byteplusapi.com",
        ),
    ],
)
def test_skill_clients_use_provider_specific_hosts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider: str,
    region: str,
    expected_host: str,
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path, provider=provider)
    hosts: list[str] = []

    def list_skill_spaces(client: Any, request: Any) -> SimpleNamespace:
        del request
        hosts.append(client.service_info.host)
        return SimpleNamespace(total_count=0, items=[])

    monkeypatch.setattr(
        "agentkit.sdk.skills.client.AgentkitSkillsClient.list_skill_spaces",
        list_skill_spaces,
    )

    with TestClient(app) as client:
        response = client.get("/web/skill-spaces", params={"region": region})

    assert response.status_code == 200
    assert hosts == [expected_host]


@pytest.mark.parametrize(
    ("provider", "expected_region", "expected_host"),
    [
        ("volcengine", "cn-beijing", "open.volcengineapi.com"),
        (
            "byteplus",
            "ap-southeast-1",
            "agentkit.ap-southeast-1.byteplusapi.com",
        ),
    ],
)
def test_skill_workbench_tool_uses_provider_specific_region_and_host(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider: str,
    expected_region: str,
    expected_host: str,
) -> None:
    monkeypatch.setenv("SANDBOX_DEV", "tool-1")
    app = _create_frontend_app(monkeypatch, tmp_path, provider=provider)
    calls: list[tuple[str, str]] = []
    _, base_url = _sandbox_model_config(provider)

    def get_tool(client: Any, request: Any) -> SimpleNamespace:
        assert request.tool_id == "tool-1"
        calls.append((client.region, client.service_info.host))
        return SimpleNamespace(
            tool_type="DevEnv",
            status="Ready",
            image_url="",
            envs=[
                SimpleNamespace(key="CODEX_MODEL", value="model-a"),
                SimpleNamespace(key="CODEX_API_KEY", value="secret"),
                SimpleNamespace(key="CODEX_BASE_URL", value=base_url),
            ],
        )

    monkeypatch.setattr(
        "agentkit.sdk.tools.client.AgentkitToolsClient.get_tool",
        get_tool,
    )

    with TestClient(app) as client:
        response = client.get("/web/skill-workbench/capabilities")

    assert response.status_code == 200
    assert response.json()["enabled"] is True
    assert calls == [(expected_region, expected_host)]


def test_list_skills_maps_existing_dto_and_pagination(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)
    calls: list[tuple[str, Any]] = []

    class _FakeSkillsClient:
        def __init__(self, **kwargs: Any) -> None:
            self.region = kwargs["region"]

        def list_skills_by_skill_space(self, request: Any) -> SimpleNamespace:
            _assert_sdk_call_is_off_event_loop()
            calls.append((self.region, request))
            return SimpleNamespace(
                total_count=12,
                items=[
                    SimpleNamespace(
                        skill_id="skill-1",
                        skill_name="工单分类",
                        skill_description="识别工单类型",
                        version="1.2.0",
                        skill_status="Published",
                    )
                ],
            )

    monkeypatch.setattr(
        "agentkit.sdk.skills.client.AgentkitSkillsClient", _FakeSkillsClient
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/skill-spaces/space-1/skills",
            params={
                "region": "cn-shanghai",
                "page": 3,
                "page_size": 5,
                "project": "ignored-project",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "skillId": "skill-1",
                "skillName": "工单分类",
                "skillDescription": "识别工单类型",
                "version": "1.2.0",
                "skillStatus": "Published",
            }
        ],
        "totalCount": 12,
        "page": 3,
        "pageSize": 5,
    }
    assert len(calls) == 1
    region, request = calls[0]
    assert region == "cn-shanghai"
    assert request.skill_space_id == "space-1"
    assert request.page_number == 3
    assert request.page_size == 5


def test_list_skills_recovers_name_addressable_items_from_dangling_relation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)

    class _DanglingRelationError(RuntimeError):
        code = "ResourceNotFound.skill"

    class _FakeSkillsClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def list_skills_by_skill_space(self, request: Any) -> SimpleNamespace:
            _assert_sdk_call_is_off_event_loop()
            del request
            raise _DanglingRelationError("dangling relation")

        def get_skill_space(self, request: Any) -> SimpleNamespace:
            assert request.id == "space-1"
            return SimpleNamespace(name="Writers")

        def list_skills_by_space_id(self, request: Any) -> SimpleNamespace:
            assert request.skill_space_id == "space-1"
            assert request.skill_space_name == "Writers"
            return SimpleNamespace(
                items=[SimpleNamespace(name="writer", description="basic")]
            )

        def get_skill_info(self, request: Any) -> SimpleNamespace:
            assert request.skill_name == "writer"
            return SimpleNamespace(
                skill_name="writer",
                description="Write content",
                skill_md="# Writer",
            )

    monkeypatch.setattr(
        "agentkit.sdk.skills.client.AgentkitSkillsClient", _FakeSkillsClient
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/skill-spaces/space-1/skills",
            params={"region": "cn-shanghai", "page": 1, "page_size": 5},
        )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "skillId": "",
                "skillName": "writer",
                "skillDescription": "Write content",
                "version": "",
                "skillStatus": "",
                "lookupByName": True,
                "degraded": True,
            }
        ],
        "totalCount": 1,
        "page": 1,
        "pageSize": 5,
        "degraded": True,
        "warnings": ["部分关联异常，已恢复可读取技能"],
    }


def test_skill_space_errors_preserve_sdk_details(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)

    class _FakeSkillsClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def list_skill_spaces(self, request: Any) -> SimpleNamespace:
            del request
            raise RuntimeError("upstream failure: signed-token-value")

    monkeypatch.setattr(
        "agentkit.sdk.skills.client.AgentkitSkillsClient", _FakeSkillsClient
    )

    with TestClient(app) as client:
        response = client.get("/web/skill-spaces", params={"region": "cn-beijing"})

    assert response.status_code == 502
    assert response.json() == {
        "detail": {
            "code": "SKILL_SERVICE_UNAVAILABLE",
            "message": "暂时无法访问 AgentKit Skills。",
            "retryable": True,
            "originalError": {
                "type": "builtins.RuntimeError",
                "message": "upstream failure: signed-token-value",
                "repr": "RuntimeError('upstream failure: signed-token-value')",
            },
        }
    }
    assert "signed-token-value" in response.text


def test_get_skill_detail_runs_sdk_call_off_event_loop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)
    calls: list[tuple[str, Any]] = []

    class _FakeSkillsClient:
        def __init__(self, **kwargs: Any) -> None:
            self.region = kwargs["region"]

        def get_skill_version(self, request: Any) -> SimpleNamespace:
            _assert_sdk_call_is_off_event_loop()
            calls.append((self.region, request))
            return SimpleNamespace(
                name="工单分类",
                description="识别工单类型",
                version="1.2.0",
                skill_md="---\nname: ticket-classifier\n---\n",
                bucket_name="",
                tos_path="",
            )

    monkeypatch.setattr(
        "agentkit.sdk.skills.client.AgentkitSkillsClient", _FakeSkillsClient
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/skill-spaces/space-1/skills/skill-1",
            params={"region": "cn-shanghai", "version": "1.2.0"},
        )

    assert response.status_code == 200
    assert response.json()["skillMd"].startswith("---")
    assert len(calls) == 1
    region, request = calls[0]
    assert region == "cn-shanghai"
    assert request.id == "skill-1"
    assert request.skill_version == "1.2.0"


def test_get_skill_detail_uses_name_lookup_for_recovered_relation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)

    class _FakeSkillsClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def get_skill_version(self, request: Any) -> SimpleNamespace:
            del request
            raise AssertionError("degraded name lookup must not invent a version id")

        def get_skill_info(self, request: Any) -> SimpleNamespace:
            _assert_sdk_call_is_off_event_loop()
            assert request.skill_name == "writer"
            assert request.skill_space_name == "Writers"
            assert request.skill_space_id == "space-1"
            return SimpleNamespace(
                skill_name="writer",
                description="Write content",
                skill_md="# Writer\n",
                bucket_name="",
                tos_path="",
            )

    monkeypatch.setattr(
        "agentkit.sdk.skills.client.AgentkitSkillsClient", _FakeSkillsClient
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/skill-spaces/space-1/skills/writer",
            params={
                "region": "cn-shanghai",
                "skill_name": "writer",
                "skill_space_name": "Writers",
            },
        )

    assert response.status_code == 200
    assert response.json()["name"] == "writer"
    assert response.json()["skillMd"] == "# Writer\n"
    assert response.json()["version"] == ""


def test_get_skill_detail_falls_back_for_legacy_skill_type(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)
    calls: list[tuple[str, Any]] = []

    class _FakeSkillsClient:
        def __init__(self, **kwargs: Any) -> None:
            self.region = kwargs["region"]

        def get_skill_version(self, request: Any) -> SimpleNamespace:
            _assert_sdk_call_is_off_event_loop()
            calls.append(("version", request))
            raise RuntimeError("interface type not consistent with skill type")

        def get_skill_info(self, request: Any) -> SimpleNamespace:
            _assert_sdk_call_is_off_event_loop()
            calls.append(("info", request))
            return SimpleNamespace(
                skill_name="cloud-migration-qa",
                description="Migration checks",
                skill_md="---\nname: cloud-migration-qa\n---\nBody.\n",
                bucket_name="",
                tos_path="",
            )

    monkeypatch.setattr(
        "agentkit.sdk.skills.client.AgentkitSkillsClient", _FakeSkillsClient
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/skill-spaces/space-1/skills/skill-1",
            params={
                "region": "cn-beijing",
                "version": "v1",
                "skill_space_name": "migration-space",
                "skill_name": "cloud-migration-qa",
            },
        )

    assert response.status_code == 200
    assert response.json()["name"] == "cloud-migration-qa"
    assert response.json()["skillMd"].endswith("Body.\n")
    assert [name for name, _request in calls] == ["version", "info"]


def test_get_skill_detail_falls_back_to_skillspace_package(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)

    class _FakeSkillsClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def get_skill_version(self, request: Any) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                name="ticket-classifier",
                description="识别工单类型",
                version="1.2.0",
                skill_md="---\nname: stale-copy\ndescription: Stale.\n---\n",
                bucket_name="skills-bucket",
                tos_path="skills/ticket-classifier.zip",
            )

    def _download_skill(
        skill: Any,
        zip_path: Path,
        *,
        region: str | None = None,
        raise_on_error: bool = False,
    ) -> bool:
        assert skill.bucket_name == "skills-bucket"
        assert skill.path == "skills/ticket-classifier.zip"
        assert region == "cn-shanghai"
        assert raise_on_error is True
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr(
                "ticket-classifier/SKILL.md",
                "---\nname: ticket-classifier\ndescription: Tickets.\n---\nBody.\n",
            )
            archive.writestr(
                "ticket-classifier/scripts/classify.py",
                "def classify(text):\n    return 'ticket'\n",
            )
        return True

    monkeypatch.setattr(
        "agentkit.sdk.skills.client.AgentkitSkillsClient", _FakeSkillsClient
    )
    monkeypatch.setattr(
        "veadk.skills.materializer._download_legacy_skill_space_skill",
        _download_skill,
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/skill-spaces/space-1/skills/skill-1",
            params={"region": "cn-shanghai", "version": "1.2.0"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["skillMd"].endswith("Body.\n")
    assert body["files"] == [
        {
            "path": "skills/ticket-classifier/SKILL.md",
            "content": body["skillMd"],
        },
        {
            "path": "skills/ticket-classifier/scripts/classify.py",
            "content": "def classify(text):\n    return 'ticket'\n",
        },
    ]


def test_get_skill_detail_skips_binary_package_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)

    class _FakeSkillsClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def get_skill_version(self, request: Any) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                name="canvas-design",
                description="Canvas design skill",
                version="v1",
                skill_md="",
                bucket_name="skills-bucket",
                tos_path="skills/canvas-design.zip",
            )

    def _download_skill(
        skill: Any,
        zip_path: Path,
        *,
        region: str | None = None,
        raise_on_error: bool = False,
    ) -> bool:
        assert skill.name == "canvas-design"
        assert region == "cn-beijing"
        assert raise_on_error is True
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr(
                "canvas-design/SKILL.md",
                "---\nname: canvas-design\ndescription: Canvas.\n---\nBody.\n",
            )
            archive.writestr(
                "canvas-design/scripts/render.py",
                "def render():\n    return 'ok'\n",
            )
            archive.writestr(
                "canvas-design/assets/font.ttf",
                b"\x00\x01\x00\x00binary-font",
            )
            archive.writestr(
                "canvas-design/assets/preview.png",
                b"\x89PNG\r\n\x1a\n\x00binary-image",
            )
        return True

    monkeypatch.setattr(
        "agentkit.sdk.skills.client.AgentkitSkillsClient", _FakeSkillsClient
    )
    monkeypatch.setattr(
        "veadk.skills.materializer._download_legacy_skill_space_skill",
        _download_skill,
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/skill-spaces/space-1/skills/skill-1",
            params={"region": "cn-beijing", "version": "v1"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["skillMd"].endswith("Body.\n")
    assert [file["path"] for file in body["files"]] == [
        "skills/canvas-design/SKILL.md",
        "skills/canvas-design/scripts/render.py",
    ]


def test_get_skill_detail_falls_back_to_skill_md_when_package_download_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)

    class _FakeSkillsClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def get_skill_version(self, request: Any) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                name="ticket-classifier",
                description="识别工单类型",
                version="1.2.0",
                skill_md="---\nname: ticket-classifier\n---\nBody.\n",
                bucket_name="skills-bucket",
                tos_path="skills/ticket-classifier.zip",
            )

    def _download_skill(
        skill: Any,
        zip_path: Path,
        *,
        region: str | None = None,
        raise_on_error: bool = False,
    ) -> bool:
        del skill, zip_path
        assert region == "cn-shanghai"
        assert raise_on_error is True
        return False

    monkeypatch.setattr(
        "agentkit.sdk.skills.client.AgentkitSkillsClient", _FakeSkillsClient
    )
    monkeypatch.setattr(
        "veadk.skills.materializer._download_legacy_skill_space_skill",
        _download_skill,
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/skill-spaces/space-1/skills/skill-1",
            params={"region": "cn-shanghai", "version": "1.2.0"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["skillMd"].endswith("Body.\n")
    assert body["files"] == []


def test_get_skill_detail_preserves_package_download_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)

    class _FakeSkillsClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def get_skill_version(self, request: Any) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                name="ticket-classifier",
                description="识别工单类型",
                version="1.2.0",
                skill_md="",
                bucket_name="skills-bucket",
                tos_path="skills/ticket-classifier.zip",
            )

    def _download_skill(*_args: Any, **_kwargs: Any) -> bool:
        raise RuntimeError("TOS GetObject failed with request-id-3")

    monkeypatch.setattr(
        "agentkit.sdk.skills.client.AgentkitSkillsClient", _FakeSkillsClient
    )
    monkeypatch.setattr(
        "veadk.skills.materializer._download_legacy_skill_space_skill",
        _download_skill,
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/skill-spaces/space-1/skills/skill-1",
            params={"region": "cn-shanghai", "version": "1.2.0"},
        )

    assert response.status_code == 502
    assert response.json()["detail"]["originalError"]["message"] == (
        "TOS GetObject failed with request-id-3"
    )


def test_skill_space_routes_keep_missing_credentials_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)
    monkeypatch.delenv("VOLCENGINE_ACCESS_KEY")
    monkeypatch.delenv("VOLCENGINE_SECRET_KEY")

    with TestClient(app) as client:
        response = client.get("/web/skill-spaces", params={"region": "cn-beijing"})

    assert response.status_code == 409
