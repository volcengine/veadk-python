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
from pathlib import Path
from types import SimpleNamespace
from threading import Lock
from typing import Any

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from veadk.cli.cli_frontend import _run_frontend_server


def _create_frontend_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    studio: bool = False,
    provider: str = "volcengine",
) -> FastAPI:
    captured: dict[str, Any] = {}
    monkeypatch.setattr("dotenv.find_dotenv", lambda *args, **kwargs: "")
    monkeypatch.setattr(
        "uvicorn.run",
        lambda app, **kwargs: captured.setdefault("app", app),
    )
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "sk")
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "bp-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "bp-sk")
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
        provider=provider,  # type: ignore[arg-type]
        studio=studio,
    )
    return captured["app"]


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = {"content-type": "application/json"}
        self.text = ""

    def json(self) -> dict[str, Any]:
        return self._payload


def test_studio_findskill_route_uses_studio_skill_catalog(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(
        monkeypatch,
        tmp_path,
        studio=True,
        provider="byteplus",
    )

    async def search_findskill(_catalog: object, **kwargs: Any) -> dict[str, object]:
        assert kwargs == {"query": "pdf", "page_number": 1, "page_size": 20}
        return {
            "items": [
                {
                    "slug": "clawhub/pdf-reader",
                    "name": "pdf-reader",
                    "description": "Read PDF files",
                    "sourceType": "clawhub",
                    "sourceRepo": "clawhub/pdf-reader",
                    "downloadCount": 42,
                    "evaluationScore": 0,
                    "version": "1.0.0",
                    "updatedAt": "2026-07-26T00:00:00+08:00",
                }
            ],
            "totalCount": 1,
        }

    monkeypatch.setattr(
        "frontend.server.studio_routes.skill_catalog.StudioSkillCatalog.search_findskill",
        search_findskill,
    )

    with TestClient(app) as client:
        response = client.get("/harness/skills/findskill?query=pdf")

    assert response.status_code == 200
    assert response.json()["items"][0]["slug"] == "clawhub/pdf-reader"


class _StorageFailure(Exception):
    def __init__(self, status: int):
        self.status_code = status


class _FakeTos:
    def __init__(self):
        self.objects = {}
        self.lock = Lock()

    def get_object(self, *, bucket, key):
        with self.lock:
            if key not in self.objects:
                raise _StorageFailure(404)
            content, etag = self.objects[key]
        return SimpleNamespace(read=io.BytesIO(content).read, etag=etag)

    def put_object(
        self, *, bucket, key, content, forbid_overwrite=False, if_match=None, **kwargs
    ):
        with self.lock:
            previous = self.objects.get(key)
            if (forbid_overwrite and previous) or (
                if_match and (not previous or previous[1] != if_match)
            ):
                raise _StorageFailure(412)
            etag = hashlib.sha256(content).hexdigest()
            self.objects[key] = content, etag
            return SimpleNamespace(etag=etag)

    def list_objects_type2(self, *, bucket, prefix, **kwargs):
        with self.lock:
            keys = sorted(key for key in self.objects if key.startswith(prefix))
        return SimpleNamespace(
            contents=[SimpleNamespace(key=key) for key in keys], is_truncated=False
        )


@pytest.fixture(params=["volcengine", "byteplus"])
def feedback_client(request, monkeypatch, tmp_path):
    provider = request.param
    region = "cn-beijing" if provider == "volcengine" else "ap-southeast-1"
    backend = _FakeTos()
    monkeypatch.setenv("VEADK_STUDIO_TOS_BUCKET", "evaluation-test")
    monkeypatch.setenv("VEADK_STUDIO_TOS_REGION", region)
    monkeypatch.setattr(
        "frontend.server.evaluation.repository.create_cached_tos_client_factory",
        lambda *args, **kwargs: lambda: backend,
    )
    app = _create_frontend_app(monkeypatch, tmp_path, studio=True, provider=provider)
    patches = []

    class RuntimeClient:
        def __init__(self, **kwargs):
            pass

        def get_runtime(self, request):
            return SimpleNamespace(
                project_name="support",
                tags=[],
                network_configurations=[
                    SimpleNamespace(
                        endpoint="https://runtime.example", network_type="public"
                    )
                ],
                authorizer_configuration=SimpleNamespace(
                    key_auth=SimpleNamespace(api_key="runtime-key"),
                    custom_jwt_authorizer=None,
                ),
            )

    class HttpClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def request(self, method, url, **kwargs):
            assert "/apps/agent/users/user-1/sessions/session-1" in url
            if method == "GET":
                return _FakeResponse(
                    {
                        "id": "session-1",
                        "state": {},
                        "events": [
                            {
                                "id": "user-event",
                                "author": "user",
                                "content": {"parts": [{"text": "问题"}]},
                            },
                            {
                                "id": "assistant-event",
                                "author": "agent",
                                "invocationId": "invocation-1",
                                "content": {"parts": [{"text": "回答"}]},
                            },
                        ],
                    }
                )
            assert method == "PATCH"
            headers = {name.lower(): value for name, value in kwargs["headers"].items()}
            assert headers["content-type"] == "application/json"
            patches.append(kwargs["json"])
            # Older Runtime gateways lack PATCH; the TOS record must remain usable
            return _FakeResponse({}, status_code=404)

        async def post(self, url, **kwargs):
            raise AssertionError(
                "Evaluation storage must not call cloud evaluation APIs"
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient", RuntimeClient
    )
    monkeypatch.setattr("httpx.AsyncClient", HttpClient)
    with TestClient(app, headers={"X-VeADK-Local-User": "user-1"}) as client:
        yield SimpleNamespace(
            client=client, backend=backend, patches=patches, region=region
        )


def _feedback(region, rating: str | None = "good"):
    return {
        "runtimeId": "runtime-1",
        "region": region,
        "appName": "agent",
        "userId": "user-1",
        "sessionId": "session-1",
        "eventId": "assistant-event",
        "rating": rating,
        "comment": "选中片段：回答\n\n批注：事实错误",
    }


def _query(region):
    return {"runtimeId": "runtime-1", "region": region, "appName": "agent"}


@pytest.mark.parametrize("rating", ["good", "bad"])
def test_message_feedback_writes_tos_and_session_state(feedback_client, rating):
    from frontend.server.evaluation.repository import sample_id

    env = feedback_client
    response = env.client.post(
        "/web/evaluation/feedback", json=_feedback(env.region, rating)
    )
    assert response.status_code == 200
    saved = response.json()
    identifier = sample_id("user", "user-1", "session-1", "assistant-event")
    assert saved["evaluationItemId"] == identifier
    assert saved["evaluationSetId"] == rating
    assert saved["statePersistence"] == "browser"
    assert saved["comment"] == _feedback(env.region)["comment"]
    state = env.patches[0]["state_delta"]["veadk_feedback:assistant-event"]
    assert state["rating"] == rating
    key = f"veadk-studio/v1/evaluation/runtime-1/samples/{identifier}.json"
    content = json.loads(env.backend.objects[key][0])
    assert content["input"] == "问题"
    assert content["output"] == "回答"
    assert content["source"] == "user"
    assert content["evaluationSetId"] == rating
    assert "appName" not in content and "agentName" not in content
    states = env.client.post(
        "/web/evaluation/feedback-state",
        json={
            "runtimeId": "runtime-1",
            "region": env.region,
            "userId": "user-1",
            "sessionId": "session-1",
            "eventIds": ["assistant-event"],
        },
    )
    assert states.status_code == 200
    assert states.json()["veadk_feedback:assistant-event"]["rating"] == rating


def test_message_feedback_reclassification_and_uncheck_use_one_tos_record(
    feedback_client,
):
    env = feedback_client
    first = env.client.post(
        "/web/evaluation/feedback", json=_feedback(env.region)
    ).json()
    changed = env.client.post(
        "/web/evaluation/feedback", json=_feedback(env.region, "bad")
    )
    assert changed.status_code == 200
    assert changed.json()["evaluationItemId"] == first["evaluationItemId"]
    rows = env.client.get(
        "/web/evaluation/feedback-cases", params=_query(env.region)
    ).json()["items"]
    assert len(rows) == 1 and rows[0]["kind"] == "bad"
    assert (
        rows[0]["score"] == 0 and rows[0]["reason"] == _feedback(env.region)["comment"]
    )
    cleared = env.client.post(
        "/web/evaluation/feedback", json=_feedback(env.region, None)
    )
    assert cleared.status_code == 200 and cleared.json()["rating"] is None
    assert (
        env.client.get(
            "/web/evaluation/feedback-cases", params=_query(env.region)
        ).json()["items"]
        == []
    )
    assert all(
        "回答" not in content.decode() for content, _ in env.backend.objects.values()
    )


def test_feedback_cases_keep_existing_page_contract_and_delete_clears_rating(
    feedback_client,
):
    env = feedback_client
    initialized = env.client.post(
        "/web/evaluation/sets/defaults", params=_query(env.region)
    )
    assert initialized.status_code == 200
    saved = env.client.post(
        "/web/evaluation/feedback", json=_feedback(env.region)
    ).json()
    response = env.client.get(
        "/web/evaluation/feedback-cases", params=_query(env.region)
    )
    assert response.status_code == 200
    body = response.json()
    assert {item["kind"] for item in body["sets"]} == {"good", "bad"}
    assert body["agentName"] == "agent"
    assert len(body["items"]) == 1
    row = body["items"][0]
    assert row["source"] == "user" and row["kind"] == "good"
    assert row["runtimeId"] == "runtime-1"
    deleted = env.client.post(
        "/web/evaluation/feedback-cases/delete",
        json={**_query(env.region), "itemIds": [saved["evaluationItemId"]]},
    )
    assert deleted.status_code == 200 and deleted.json()["deletedCount"] == 1
    assert (
        env.patches[-1]["state_delta"]["veadk_feedback:assistant-event"]["rating"]
        is None
    )
    assert (
        env.client.get(
            "/web/evaluation/feedback-cases", params=_query(env.region)
        ).json()["items"]
        == []
    )


def test_feedback_rejects_another_users_session(feedback_client):
    env = feedback_client
    response = env.client.post(
        "/web/evaluation/feedback",
        json={**_feedback(env.region), "userId": "another-user"},
    )
    assert response.status_code == 403
    assert not env.backend.objects
