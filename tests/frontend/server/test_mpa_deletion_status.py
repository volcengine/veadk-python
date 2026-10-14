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

"""MPA deletion confirmation never turns uncertain cloud reads into success."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from agentkit.toolkit.errors import ApiError
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from frontend.server.mpa_deletion_status import mount_mpa_deletion_status


def missing():
    return ApiError("Runtime missing", error_code="InvalidAgentKitRuntime.NotFound")


def setup():
    app = FastAPI()
    credentials = Mock(return_value=("test-ak", "test-secret", ""))
    get_runtime = Mock(side_effect=missing())
    list_page = Mock(return_value={"AgentKitRuntimes": []})

    def owner(request):
        user = request.headers.get("x-test-user", "developer")
        if user == "viewer":
            raise HTTPException(403, "Agent management is not allowed")
        return user

    remember = mount_mpa_deletion_status(
        app,
        owner=owner,
        get_runtime=get_runtime,
        list_page=list_page,
        credentials=credentials,
        region=lambda value: value,
    )

    @app.post("/fixture/start")
    def start(request: Request):
        remember(request, "r-one", "cn-beijing")
        return {}

    client = TestClient(app)
    client.post("/fixture/start")
    return client, credentials, get_runtime, list_page


def check(client, **kwargs):
    return client.get(
        "/web/mpa-runtime-deletion-status",
        params={"runtimeId": "r-one", "region": "cn-beijing"},
        **kwargs,
    )


def test_deleted_requires_not_found_and_all_pages_absent():
    client, _, get_runtime, pages = setup()
    pages.side_effect = [
        {"AgentKitRuntimes": [{"RuntimeId": "r-other"}], "NextToken": "next"},
        {"AgentKitRuntimes": []},
    ]
    response = check(client)
    assert response.json() == {"deleted": True}
    assert response.headers["cache-control"] == "no-store"
    assert pages.call_args_list[1].args == ("cn-beijing", "next")
    get_runtime.assert_called_once()


@pytest.mark.parametrize("listed", [False, True])
def test_present_runtime_never_means_deleted(listed):
    client, _, get_runtime, pages = setup()
    if listed:
        pages.return_value = {"AgentKitRuntimes": [{"RuntimeId": "r-one"}]}
    else:
        get_runtime.side_effect = None
        get_runtime.return_value = SimpleNamespace(runtime_id="r-one")
    assert check(client).json() == {"deleted": False}
    if not listed:
        pages.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        HTTPException(404, "runtime_access_denied"),
        ApiError("private token must not leak", error_code="AccessDenied"),
        TimeoutError("private token must not leak"),
        RuntimeError("InvalidAgentKitRuntime.NotFound appears in unrelated text"),
    ],
)
def test_query_errors_fail_closed_and_never_leak_exception(error):
    client, _, get_runtime, pages = setup()
    get_runtime.side_effect = error
    response = check(client)
    assert response.status_code in {404, 503}
    assert "private token" not in response.text
    assert "deleted" not in response.json()
    pages.assert_not_called()


def test_wrapped_structured_provider_error_is_recognized():
    client, _, get_runtime, _ = setup()
    cause = Exception(
        json.dumps(
            {"ResponseMetadata": {"Error": {"Code": "InvalidAgentKitRuntime.NotFound"}}}
        ).encode()
    )
    wrapped = ApiError("Failed to GetRuntime")
    wrapped.__cause__ = cause
    get_runtime.side_effect = wrapped
    assert check(client).json() == {"deleted": True}


@pytest.mark.parametrize(
    "page",
    [
        {"AgentKitRuntimes": [], "NextToken": "repeat"},
        {},
        {"AgentKitRuntimes": [{"Name": "missing identity"}]},
        {"AgentKitRuntimes": "invalid"},
        {"AgentKitRuntimes": [], "NextToken": 0},
    ],
)
def test_incomplete_or_invalid_listing_never_means_deleted(page):
    client, _, _, pages = setup()
    pages.return_value = page
    assert check(client).status_code == 503
    assert pages.call_count <= 2


def test_permission_failure_in_list_never_means_deleted():
    client, _, _, pages = setup()
    pages.side_effect = ApiError("denied", error_code="AccessDenied")
    assert check(client).status_code == 503


@pytest.mark.parametrize("user", ["viewer", "another-developer"])
def test_confirmation_is_scoped_to_authorized_studio_owner(user):
    client, _, get_runtime, pages = setup()
    response = check(client, headers={"x-test-user": user})
    assert response.status_code in {403, 503}
    get_runtime.assert_not_called()
    pages.assert_not_called()


@pytest.mark.parametrize("during_query", [False, True])
def test_credential_changes_never_mean_deleted(during_query):
    client, credentials, get_runtime, pages = setup()
    if during_query:

        def rotate(_region, _token):
            credentials.return_value = ("changed-ak", "changed-secret", "")
            return {"AgentKitRuntimes": []}

        pages.side_effect = rotate
    else:
        credentials.return_value = ("changed-ak", "changed-secret", "")
    assert check(client).status_code == 503
    if not during_query:
        get_runtime.assert_not_called()


def test_unrelated_scope_and_expired_context_fail_closed(monkeypatch):
    from frontend.server import mpa_deletion_status as module

    client, _, get_runtime, _ = setup()
    response = client.get(
        "/web/mpa-runtime-deletion-status",
        params={"runtimeId": "r-other", "region": "cn-beijing"},
    )
    assert response.status_code == 503
    response = client.get(
        "/web/mpa-runtime-deletion-status",
        params={"runtimeId": "r-one", "region": "cn-shanghai"},
    )
    assert response.status_code == 503
    monkeypatch.setattr(module, "_CONTEXT_TTL", -1)
    assert check(client).status_code == 503
    get_runtime.assert_not_called()


def test_pagination_budget_is_bounded():
    client, _, _, pages = setup()
    pages.side_effect = lambda _region, _token: {
        "AgentKitRuntimes": [],
        "NextToken": str(pages.call_count),
    }
    assert check(client).status_code == 503
    assert pages.call_count == 20


def test_context_count_is_bounded(monkeypatch):
    from frontend.server import mpa_deletion_status as module

    monkeypatch.setattr(module, "_CONTEXT_LIMIT", 1)
    client, _, get_runtime, _ = setup()
    client.post("/fixture/start", headers={"x-test-user": "another-developer"})
    assert check(client).status_code == 503
    get_runtime.assert_not_called()


def test_explicit_permission_error_overrides_wrapped_not_found():
    client, _, get_runtime, _ = setup()
    error = ApiError("denied", error_code="AccessDenied")
    error.__cause__ = missing()
    get_runtime.side_effect = error
    assert check(client).status_code == 503


@pytest.mark.parametrize("mpa", [False, True])
def test_studio_route_registers_confirmation_only_for_actual_mpa(
    monkeypatch, tmp_path, mpa
):
    from unittest.mock import AsyncMock
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient
    from agentkit.sdk.runtime.types import ListRuntimesResponse
    from frontend.server.mpa.runtime_client import MpaRuntimeClient
    from tests.cli.test_studio_rbac import (
        _create_studio_app,
        _runtime,
        _runtime_with_public_endpoint,
    )

    runtime = _runtime_with_public_endpoint(_runtime("r-delete-status", "developer"))
    if mpa:
        runtime.tags.append(SimpleNamespace(key="veadk:agent-type", value="mpa"))
    removed = []

    def get_runtime(_self, _request):
        if removed:
            raise missing()
        return runtime

    monkeypatch.setattr(AgentkitRuntimeClient, "get_runtime", get_runtime)
    monkeypatch.setattr(
        AgentkitRuntimeClient,
        "delete_runtime",
        lambda _self, _request: removed.append(runtime.runtime_id),
    )
    monkeypatch.setattr(
        AgentkitRuntimeClient,
        "list_runtimes",
        lambda _self, _request: ListRuntimesResponse(),
    )
    monkeypatch.setattr(MpaRuntimeClient, "list_sessions", AsyncMock(return_value=[]))
    app = _create_studio_app(monkeypatch, tmp_path, developers="developer")
    headers = {"X-VeADK-Local-User": "developer"}
    with TestClient(app) as client:
        response = client.post(
            "/web/delete-runtime",
            headers=headers,
            json={
                "runtimeId": runtime.runtime_id,
                "region": "cn-beijing",
                "agentCategory": "mpa",
            },
        )
        assert response.status_code == 200, response.text
        assert removed == [runtime.runtime_id]
        status = client.get(
            "/web/mpa-runtime-deletion-status",
            headers=headers,
            params={"runtimeId": runtime.runtime_id, "region": "cn-beijing"},
        )
    if mpa:
        assert status.status_code == 200, status.text
        assert status.json() == {"deleted": True}
    else:
        assert status.status_code == 503


def test_status_timeout_remains_unconfirmed(monkeypatch):
    from frontend.server import mpa_deletion_status as module

    client, _, _, _ = setup()
    monkeypatch.setattr(module, "_CHECK_TIMEOUT", 0)
    response = check(client)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "mpa_deletion_unconfirmed"
