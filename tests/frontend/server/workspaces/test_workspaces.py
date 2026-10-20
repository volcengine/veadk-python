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
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from frontend.server.environments.repository import TosEnvironmentRepository
from frontend.server.environments.routes import mount_environment_routes
from frontend.server.environments.service import EnvironmentService
from frontend.server.workspaces.repository import TosWorkspaceRepository
from frontend.server.workspaces.routes import mount_workspace_routes
from frontend.server.workspaces.service import WorkspaceService


class _TosError(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"TOS {status_code}")


class FakeTos:
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


def _environment_payload(name: str) -> dict[str, object]:
    return {
        "name": name,
        "description": "",
        "operatingSystem": "ubuntu-22.04",
        "language": "python-3.12",
        "optionIds": [],
    }


def test_workspaces_group_reusable_environments_without_owning_them():
    tos = FakeTos()
    environment_repository = TosEnvironmentRepository(
        bucket="studio", client_factory=lambda: tos
    )
    workspace_repository = TosWorkspaceRepository(
        bucket="studio", client_factory=lambda: tos
    )
    workspace_service = WorkspaceService(workspace_repository, environment_repository)
    environment_service = EnvironmentService(
        environment_repository, None, workspace_references=workspace_service
    )
    app = FastAPI()
    mount_environment_routes(app, environment_service, lambda _request: "owner")
    mount_workspace_routes(app, workspace_service, lambda _request: "owner")
    client = TestClient(app)

    first = client.post("/web/environments", json=_environment_payload("Python"))
    second = client.post("/web/environments", json=_environment_payload("Browser"))
    assert first.status_code == 201
    assert second.status_code == 201
    first_id = first.json()["id"]
    second_id = second.json()["id"]

    created = client.post(
        "/web/workspaces",
        json={
            "name": "内容生产",
            "description": "共享开发工具",
            "environmentIds": [first_id, second_id, first_id],
        },
    )
    assert created.status_code == 201
    workspace = created.json()
    assert workspace["environmentIds"] == [first_id, second_id]
    workspace_id = workspace["id"]

    reused = client.post(
        "/web/workspaces",
        json={"name": "网页测试", "environmentIds": [second_id]},
    )
    assert reused.status_code == 201
    assert reused.json()["environmentIds"] == [second_id]

    removed = client.delete(f"/web/workspaces/{workspace_id}/environments/{first_id}")
    assert removed.status_code == 200
    assert removed.json()["environmentIds"] == [second_id]

    added = client.put(f"/web/workspaces/{workspace_id}/environments/{first_id}")
    assert added.status_code == 200
    assert added.json()["environmentIds"] == [second_id, first_id]

    listed = client.get("/web/workspaces").json()["items"]
    assert {item["name"] for item in listed} == {"内容生产", "网页测试"}
    assert any("/workspaces/owner/" in key for key in tos.objects)


def test_workspace_rejects_unknown_environment_and_environment_delete_when_referenced():
    tos = FakeTos()
    environment_repository = TosEnvironmentRepository(
        bucket="studio", client_factory=lambda: tos
    )
    workspace_repository = TosWorkspaceRepository(
        bucket="studio", client_factory=lambda: tos
    )
    workspace_service = WorkspaceService(workspace_repository, environment_repository)
    environment_service = EnvironmentService(
        environment_repository, None, workspace_references=workspace_service
    )
    app = FastAPI()
    mount_environment_routes(app, environment_service, lambda _request: "owner")
    mount_workspace_routes(app, workspace_service, lambda _request: "owner")
    client = TestClient(app)

    invalid = client.post(
        "/web/workspaces",
        json={"name": "无效工作区", "environmentIds": ["0" * 32]},
    )
    assert invalid.status_code == 400

    environment_id = client.post(
        "/web/environments", json=_environment_payload("共享环境")
    ).json()["id"]
    workspace = client.post(
        "/web/workspaces",
        json={"name": "共享工作区", "environmentIds": [environment_id]},
    ).json()

    blocked = client.delete(f"/web/environments/{environment_id}")
    assert blocked.status_code == 409
    assert "共享工作区" in blocked.json()["detail"]

    assert client.delete(f"/web/workspaces/{workspace['id']}").status_code == 204
    assert client.delete(f"/web/environments/{environment_id}").status_code == 204
