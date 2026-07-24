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

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from veadk.cli.cli_frontend import _run_frontend_server


def _create_frontend_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FastAPI:
    captured: dict[str, Any] = {}
    monkeypatch.setattr("dotenv.find_dotenv", lambda: "")
    monkeypatch.setattr(
        "uvicorn.run",
        lambda app, **kwargs: captured.setdefault("app", app),
    )
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
        open_browser=False,
    )
    return captured["app"]


def _assert_sdk_call_is_off_event_loop() -> None:
    with pytest.raises(RuntimeError, match="no running event loop"):
        asyncio.get_running_loop()


def test_list_a2a_spaces_paginates_and_maps_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)
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


def test_list_skill_spaces_keeps_cross_region_defaults(
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
    assert response.json()["totalCount"] == 2
    assert response.json()["page"] == 1
    assert response.json()["pageSize"] == 50
    assert {item["region"] for item in response.json()["items"]} == {
        "cn-beijing",
        "cn-shanghai",
    }
    assert {region for region, _ in calls} == {"cn-beijing", "cn-shanghai"}
    assert all(request.page_number == 1 for _, request in calls)
    assert all(request.page_size == 50 for _, request in calls)
    assert all(request.project_name is None for _, request in calls)


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


def test_skill_space_errors_do_not_expose_sdk_details(
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
        "detail": "暂时无法加载 AgentKit Skill Space，请稍后重试。"
    }
    assert "signed-token-value" not in response.text


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
                bucket_name="skills-bucket",
                tos_path="skills/ticket-classifier.zip",
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


def test_skill_space_routes_keep_missing_credentials_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)
    monkeypatch.delenv("VOLCENGINE_ACCESS_KEY")
    monkeypatch.delenv("VOLCENGINE_SECRET_KEY")

    with TestClient(app) as client:
        response = client.get("/web/skill-spaces", params={"region": "cn-beijing"})

    assert response.status_code == 409
