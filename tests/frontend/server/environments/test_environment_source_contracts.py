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

"""API contract tests for external environment image sources."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from frontend.server.environments.git_repository import RepositorySnapshot
from frontend.server.environments.models import (
    EnvironmentInput,
    GitSource,
    RepositoryInspection,
)
from frontend.server.environments.routes import mount_environment_routes
from frontend.server.environments.service import EnvironmentService


def _payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Repository environment",
        "description": "",
        "operatingSystem": "ubuntu-24.04",
        "language": "python-3.12",
        "optionIds": [],
        "selectedSkills": [],
    }
    payload.update(updates)
    return payload


class _Inspector:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def inspect(self, repository_url: str, ref: str = "") -> RepositoryInspection:
        self.calls.append((repository_url, ref))
        return RepositoryInspection(
            repositoryUrl=repository_url,
            ref=ref,
            commitSha="a" * 40,
            dockerfiles=["Dockerfile", "deploy/Agent.Dockerfile"],
        )

    def snapshot(self, source: GitSource) -> RepositorySnapshot:
        raise NotImplementedError


def test_git_source_and_cp_repository_keep_the_public_api_shape() -> None:
    body = EnvironmentInput.model_validate(
        _payload(
            gitSource={
                "repositoryUrl": "https://github.com/example/public-agent.git",
                "ref": "release/v1",
                "dockerfilePath": "deploy/Agent.Dockerfile",
            },
            containerRepository={
                "region": "cn-beijing",
                "registry": "team-registry",
                "namespace": "agents",
                "repository": "runtime-environments",
            },
        )
    )

    dumped = body.model_dump(mode="json", by_alias=True)

    assert dumped["gitSource"] == {
        "repositoryUrl": "https://github.com/example/public-agent.git",
        "ref": "release/v1",
        "dockerfilePath": "deploy/Agent.Dockerfile",
    }
    assert dumped["containerRepository"] == {
        "region": "cn-beijing",
        "registry": "team-registry",
        "namespace": "agents",
        "repository": "runtime-environments",
    }
    assert dumped["imageSource"] is None


def test_repository_inspection_route_uses_the_public_camel_case_contract() -> None:
    inspector = _Inspector()
    service = EnvironmentService(None, None, git_inspector=inspector)
    app = FastAPI()
    mount_environment_routes(app, service, lambda _request: "owner")

    response = TestClient(app).post(
        "/web/environment-repositories/inspect",
        json={
            "repositoryUrl": "https://github.com/example/public-agent.git",
            "ref": "main",
        },
    )

    assert response.status_code == 200
    assert inspector.calls == [("https://github.com/example/public-agent.git", "main")]
    assert response.json() == {
        "repositoryUrl": "https://github.com/example/public-agent.git",
        "ref": "main",
        "commitSha": "a" * 40,
        "dockerfiles": ["Dockerfile", "deploy/Agent.Dockerfile"],
    }


def test_existing_image_source_keeps_repository_and_reference_separate() -> None:
    body = EnvironmentInput.model_validate(
        _payload(
            imageSource={
                "region": "ap-southeast-1",
                "registry": "production",
                "namespace": "agents",
                "repository": "support-agent",
                "reference": "2026-08-31",
            }
        )
    )

    assert body.model_dump(mode="json", by_alias=True)["imageSource"] == {
        "region": "ap-southeast-1",
        "registry": "production",
        "namespace": "agents",
        "repository": "support-agent",
        "reference": "2026-08-31",
    }


def test_git_build_and_existing_image_are_mutually_exclusive() -> None:
    with pytest.raises(ValidationError, match="不能同时配置"):
        EnvironmentInput.model_validate(
            _payload(
                gitSource={
                    "repositoryUrl": "https://github.com/example/public-agent.git",
                    "dockerfilePath": "Dockerfile",
                },
                imageSource={
                    "region": "cn-beijing",
                    "registry": "production",
                    "namespace": "agents",
                    "repository": "support-agent",
                    "reference": "stable",
                },
            )
        )


def test_cp_repository_requires_a_git_source() -> None:
    with pytest.raises(ValidationError, match="仅代码仓库构建"):
        EnvironmentInput.model_validate(
            _payload(
                containerRepository={
                    "region": "cn-beijing",
                    "registry": "production",
                    "namespace": "agents",
                    "repository": "support-agent",
                }
            )
        )


def test_git_dockerfile_path_cannot_escape_the_repository() -> None:
    with pytest.raises(ValidationError, match="Dockerfile 路径必须是仓库内"):
        EnvironmentInput.model_validate(
            _payload(
                gitSource={
                    "repositoryUrl": "https://github.com/example/public-agent.git",
                    "dockerfilePath": "../Dockerfile",
                }
            )
        )
