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


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = {"content-type": "application/json"}
        self.text = ""

    def json(self) -> dict[str, Any]:
        return self._payload


def test_message_feedback_writes_dataset_and_session_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)
    openapi_calls: list[dict[str, Any]] = []
    session_patches: list[dict[str, Any]] = []

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def get_runtime(self, request: Any) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                project_name="support",
                tags=[],
                network_configurations=[
                    SimpleNamespace(
                        endpoint="https://runtime.example",
                        network_type="public",
                    )
                ],
                authorizer_configuration=SimpleNamespace(
                    key_auth=SimpleNamespace(api_key="runtime-key"),
                    custom_jwt_authorizer=None,
                ),
            )

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            del args

        async def request(self, method: str, url: str, **kwargs: Any) -> _FakeResponse:
            if method == "GET" and "/sessions/session-1" in url:
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
            if method == "GET" and "/web/agent-info/agent" in url:
                return _FakeResponse({"name": "客服助手"})
            if method == "PATCH" and "/sessions/session-1" in url:
                session_patches.append(kwargs["json"])
                return _FakeResponse({}, status_code=404)
            raise AssertionError((method, url))

        async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
            del url
            action = kwargs["params"]["Action"]
            openapi_calls.append(
                {
                    "action": action,
                    "params": kwargs["params"],
                    "body": kwargs["content"],
                }
            )
            if action == "ListEvaluationSets":
                return _FakeResponse(
                    {
                        "Result": {
                            "EvaluationSets": [
                                {
                                    "Id": "set-1",
                                    "Name": "客服助手_good_case",
                                    "WorkspaceId": "workspace-1",
                                }
                            ]
                        }
                    }
                )
            if action == "BatchCreateEvaluationSetItems":
                return _FakeResponse(
                    {
                        "Result": {
                            "ItemOutputs": [
                                {
                                    "ItemId": "item-1",
                                    "ItemKey": "stable-key",
                                    "IsNewItem": True,
                                }
                            ]
                        }
                    }
                )
            raise AssertionError(action)

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FakeRuntimeClient,
    )
    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    with TestClient(app) as client:
        response = client.post(
            "/web/evaluation/feedback",
            headers={"X-VeADK-Local-User": "user-1"},
            json={
                "runtimeId": "runtime-1",
                "region": "cn-beijing",
                "appName": "agent",
                "userId": "user-1",
                "sessionId": "session-1",
                "eventId": "assistant-event",
                "rating": "good",
            },
        )

    assert response.status_code == 200
    assert response.json()["rating"] == "good"
    assert response.json()["evaluationItemId"] == "item-1"
    assert response.json()["statePersistence"] == "browser"
    assert [call["action"] for call in openapi_calls] == [
        "ListEvaluationSets",
        "ListEvaluationSets",
        "BatchCreateEvaluationSetItems",
        "ListEvaluationSets",
        "ListEvaluationSets",
    ]
    assert openapi_calls[0]["params"]["ProjectName"] == "support"
    assert openapi_calls[1]["params"]["WorkspaceId"] == "workspace-1"
    state = session_patches[0]["state_delta"]["veadk_feedback:assistant-event"]
    assert state["rating"] == "good"
    assert state["evaluationItemId"] == "item-1"


def test_message_feedback_uncheck_deletes_case_by_stable_item_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from veadk.integrations.agentkit.evaluation.feedback import feedback_item_key

    app = _create_frontend_app(monkeypatch, tmp_path)
    openapi_calls: list[dict[str, Any]] = []
    session_patches: list[dict[str, Any]] = []
    stable_key = feedback_item_key(
        project_name="support",
        runtime_id="runtime-1",
        session_id="session-1",
        message_id="assistant-event",
    )

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def get_runtime(self, request: Any) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                project_name="support",
                tags=[],
                network_configurations=[
                    SimpleNamespace(
                        endpoint="https://runtime.example",
                        network_type="public",
                    )
                ],
                authorizer_configuration=SimpleNamespace(
                    key_auth=SimpleNamespace(api_key="runtime-key"),
                    custom_jwt_authorizer=None,
                ),
            )

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            del args

        async def request(self, method: str, url: str, **kwargs: Any) -> _FakeResponse:
            if method == "GET" and "/sessions/session-1" in url:
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
                                "content": {"parts": [{"text": "回答"}]},
                            },
                        ],
                    }
                )
            if method == "GET" and "/web/agent-info/agent" in url:
                return _FakeResponse({"name": "客服助手"})
            if method == "PATCH" and "/sessions/session-1" in url:
                session_patches.append(kwargs["json"])
                return _FakeResponse({})
            raise AssertionError((method, url))

        async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
            del url
            action = kwargs["params"]["Action"]
            body = kwargs["content"].decode("utf-8")
            openapi_calls.append(
                {
                    "action": action,
                    "params": kwargs["params"],
                    "body": body,
                }
            )
            if action == "ListEvaluationSets":
                if "客服助手_good_case" in body:
                    return _FakeResponse(
                        {
                            "Result": {
                                "EvaluationSets": [
                                    {
                                        "Id": "good-set",
                                        "Name": "客服助手_good_case",
                                        "WorkspaceId": "workspace-1",
                                    }
                                ]
                            }
                        }
                    )
                if "客服助手_bad_case" in body:
                    return _FakeResponse({"Result": {"EvaluationSets": []}})
                return _FakeResponse(
                    {
                        "Result": {
                            "EvaluationSets": [
                                {
                                    "Id": "probe-set",
                                    "Name": "其他评测集",
                                    "WorkspaceId": "workspace-1",
                                }
                            ]
                        }
                    }
                )
            if action == "ListEvaluationSetItems":
                return _FakeResponse(
                    {
                        "Result": {
                            "Items": [
                                {
                                    "ItemId": "good-item",
                                    "ItemKey": stable_key,
                                    "Turns": [{"FieldDataList": []}],
                                }
                            ]
                        }
                    }
                )
            if action == "BatchDeleteEvaluationSetItems":
                assert kwargs["params"]["EvaluationSetId"] == "good-set"
                assert '"good-item"' in body
                return _FakeResponse({"Result": {}})
            raise AssertionError(action)

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FakeRuntimeClient,
    )
    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    with TestClient(app) as client:
        response = client.post(
            "/web/evaluation/feedback",
            headers={"X-VeADK-Local-User": "user-1"},
            json={
                "runtimeId": "runtime-1",
                "region": "cn-beijing",
                "appName": "agent",
                "userId": "user-1",
                "sessionId": "session-1",
                "eventId": "assistant-event",
                "rating": None,
            },
        )

    assert response.status_code == 200
    assert response.json()["rating"] is None
    assert "BatchDeleteEvaluationSetItems" in [
        call["action"] for call in openapi_calls
    ]
    patch = session_patches[0]["state_delta"]["veadk_feedback:assistant-event"]
    assert patch["rating"] is None
    assert patch["evaluationItemId"] is None


def test_feedback_cases_list_agentkit_dataset_items(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)
    openapi_calls: list[dict[str, Any]] = []

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def get_runtime(self, request: Any) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                project_name="support",
                tags=[],
                network_configurations=[
                    SimpleNamespace(
                        endpoint="https://runtime.example",
                        network_type="public",
                    )
                ],
                authorizer_configuration=SimpleNamespace(
                    key_auth=SimpleNamespace(api_key="runtime-key"),
                    custom_jwt_authorizer=None,
                ),
            )

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            del args

        async def request(self, method: str, url: str, **kwargs: Any) -> _FakeResponse:
            del kwargs
            if method == "GET" and "/web/agent-info/agent" in url:
                return _FakeResponse({"name": "客服助手"})
            raise AssertionError((method, url))

        async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
            del url
            action = kwargs["params"]["Action"]
            body = kwargs["content"].decode("utf-8")
            openapi_calls.append(
                {
                    "action": action,
                    "params": kwargs["params"],
                    "body": body,
                }
            )
            if action == "ListEvaluationSets":
                if "客服助手_good_case" in body:
                    return _FakeResponse(
                        {
                            "Result": {
                                "EvaluationSets": [
                                    {
                                        "Id": "good-set",
                                        "Name": "客服助手_good_case",
                                        "WorkspaceId": "workspace-1",
                                    }
                                ]
                            }
                        }
                    )
                if "客服助手_bad_case" in body:
                    return _FakeResponse(
                        {
                            "Result": {
                                "EvaluationSets": [
                                    {
                                        "Id": "bad-set",
                                        "Name": "客服助手_bad_case",
                                        "WorkspaceId": "workspace-1",
                                    }
                                ]
                            }
                        }
                    )
                return _FakeResponse(
                    {
                        "Result": {
                            "EvaluationSets": [
                                {
                                    "Id": "probe-set",
                                    "Name": "其他评测集",
                                    "WorkspaceId": "workspace-1",
                                }
                            ]
                        }
                    }
                )
            if action == "ListEvaluationSetItems":
                set_id = kwargs["params"]["EvaluationSetId"]
                rating = "good" if set_id == "good-set" else "bad"
                return _FakeResponse(
                    {
                        "Result": {
                            "Items": [
                                {
                                    "ItemId": f"{rating}-item",
                                    "ItemKey": f"{rating}-key",
                                    "Turns": [
                                        {
                                            "FieldDataList": [
                                                {
                                                    "Key": "input",
                                                    "Content": {"Text": "问题"},
                                                },
                                                {
                                                    "Key": "output",
                                                    "Content": {"Text": "回答"},
                                                },
                                                {
                                                    "Key": "user_id",
                                                    "Content": {"Text": "user-1"},
                                                },
                                            ]
                                        }
                                    ],
                                }
                            ]
                        }
                    }
                )
            raise AssertionError(action)

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FakeRuntimeClient,
    )
    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    with TestClient(app) as client:
        response = client.get(
            "/web/evaluation/feedback-cases",
            headers={"X-VeADK-Local-User": "user-1"},
            params={
                "runtimeId": "runtime-1",
                "region": "cn-beijing",
                "appName": "agent",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["agentName"] == "客服助手"
    assert {item["kind"] for item in payload["items"]} == {"good", "bad"}
    assert payload["items"][0]["input"] == "问题"
    assert [call["action"] for call in openapi_calls] == [
        "ListEvaluationSets",
        "ListEvaluationSets",
        "ListEvaluationSetItems",
        "ListEvaluationSets",
        "ListEvaluationSetItems",
    ]
    assert openapi_calls[2]["params"]["EvaluationSetId"] == "good-set"
    assert openapi_calls[4]["params"]["EvaluationSetId"] == "bad-set"


def test_feedback_cases_delete_removes_dataset_items_and_clears_rating(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)
    openapi_calls: list[dict[str, Any]] = []
    session_patches: list[dict[str, Any]] = []

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def get_runtime(self, request: Any) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                project_name="support",
                tags=[],
                network_configurations=[
                    SimpleNamespace(
                        endpoint="https://runtime.example",
                        network_type="public",
                    )
                ],
                authorizer_configuration=SimpleNamespace(
                    key_auth=SimpleNamespace(api_key="runtime-key"),
                    custom_jwt_authorizer=None,
                ),
            )

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            del args

        async def request(self, method: str, url: str, **kwargs: Any) -> _FakeResponse:
            if method == "GET" and "/web/agent-info/agent" in url:
                return _FakeResponse({"name": "客服助手"})
            if method == "PATCH" and "/sessions/session-1" in url:
                session_patches.append(kwargs["json"])
                return _FakeResponse({})
            raise AssertionError((method, url))

        async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
            del url
            action = kwargs["params"]["Action"]
            body = kwargs["content"].decode("utf-8")
            openapi_calls.append(
                {
                    "action": action,
                    "params": kwargs["params"],
                    "body": body,
                }
            )
            if action == "ListEvaluationSets":
                if "客服助手_good_case" in body:
                    return _FakeResponse(
                        {
                            "Result": {
                                "EvaluationSets": [
                                    {
                                        "Id": "good-set",
                                        "Name": "客服助手_good_case",
                                        "WorkspaceId": "workspace-1",
                                    }
                                ]
                            }
                        }
                    )
                if "客服助手_bad_case" in body:
                    return _FakeResponse({"Result": {"EvaluationSets": []}})
                return _FakeResponse(
                    {
                        "Result": {
                            "EvaluationSets": [
                                {
                                    "Id": "probe-set",
                                    "Name": "其他评测集",
                                    "WorkspaceId": "workspace-1",
                                }
                            ]
                        }
                    }
                )
            if action == "ListEvaluationSetItems":
                return _FakeResponse(
                    {
                        "Result": {
                            "Items": [
                                {
                                    "ItemId": "good-item",
                                    "ItemKey": "good-key",
                                    "Turns": [
                                        {
                                            "FieldDataList": [
                                                {
                                                    "Key": "session_id",
                                                    "Content": {"Text": "session-1"},
                                                },
                                                {
                                                    "Key": "message_id",
                                                    "Content": {"Text": "assistant-event"},
                                                },
                                                {
                                                    "Key": "user_id",
                                                    "Content": {"Text": "user-1"},
                                                },
                                            ]
                                        }
                                    ],
                                }
                            ]
                        }
                    }
                )
            if action == "BatchDeleteEvaluationSetItems":
                assert kwargs["params"]["EvaluationSetId"] == "good-set"
                assert kwargs["params"]["WorkspaceId"] == "workspace-1"
                assert '"good-item"' in body
                return _FakeResponse({"Result": {}})
            raise AssertionError(action)

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FakeRuntimeClient,
    )
    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    with TestClient(app) as client:
        response = client.post(
            "/web/evaluation/feedback-cases/delete",
            headers={"X-VeADK-Local-User": "user-1"},
            json={
                "runtimeId": "runtime-1",
                "region": "cn-beijing",
                "appName": "agent",
                "itemIds": ["good-item"],
            },
        )

    assert response.status_code == 200
    assert response.json()["deletedCount"] == 1
    assert "BatchDeleteEvaluationSetItems" in [
        call["action"] for call in openapi_calls
    ]
    feedback_patch = session_patches[0]["state_delta"][
        "veadk_feedback:assistant-event"
    ]
    assert feedback_patch["rating"] is None
    assert feedback_patch["evaluationItemId"] is None
    assert feedback_patch["syncStatus"] == "synced"


def test_message_feedback_rejects_another_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)

    with TestClient(app) as client:
        response = client.post(
            "/web/evaluation/feedback",
            headers={"X-VeADK-Local-User": "user-1"},
            json={
                "runtimeId": "runtime-1",
                "appName": "agent",
                "userId": "user-2",
                "sessionId": "session-1",
                "eventId": "assistant-event",
                "rating": "bad",
            },
        )

    assert response.status_code == 403
