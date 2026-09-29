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

import json
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from frontend.server.runtime_artifacts import (
    RuntimeArtifactAccess,
    RuntimeArtifactError,
    RuntimeArtifactService,
    mount_routes,
)
from frontend.server.runtime_artifacts.runtime_detail import (
    read_runtime_artifact_detail,
)


class _RawClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.requests: list[dict[str, Any]] = []

    def _invoke_api(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        # Match the real SDK boundary where the supplied response type validates
        # the raw Result object before returning it to callers
        return kwargs["response_type"].model_validate(self.payload)


def test_runtime_detail_projects_only_mount_metadata_from_raw_sdk_payload() -> None:
    client = _RawClient(
        {
            "RuntimeId": "r-one",
            "EnvironmentVariables": [
                {"Key": "MODEL_AGENT_API_KEY", "Value": "model-secret"}
            ],
            "AuthorizerConfiguration": {"Secret": "auth-secret"},
            "TosMountConfig": {
                "EnableTos": True,
                "Credentials": {
                    "AccessKeyId": "mount-ak",
                    "SecretAccessKey": "mount-sk",
                },
                "MountPoints": [
                    {
                        "BucketName": "private-bucket",
                        "BucketPath": "/",
                        "LocalMountPath": "/mnt/artifacts",
                        "Endpoint": "http://private-endpoint",
                        "Credentials": {"SecretAccessKey": "nested-secret"},
                    }
                ],
            },
        }
    )

    detail = read_runtime_artifact_detail(client, "r-one")

    assert client.requests[0]["api_action"] == "GetRuntime"
    assert client.requests[0]["request"].runtime_id == "r-one"
    assert detail == {
        "TosMountConfig": {
            "EnableTos": True,
            "MountPoints": [
                {
                    "BucketName": "private-bucket",
                    "BucketPath": "/",
                    "LocalMountPath": "/mnt/artifacts",
                }
            ],
        }
    }
    serialized = json.dumps(detail)
    assert all(
        secret not in serialized
        for secret in [
            "model-secret",
            "auth-secret",
            "mount-ak",
            "mount-sk",
            "nested-secret",
            "private-endpoint",
        ]
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"TosMountConfig": {"EnableTos": {"SecretAccessKey": "response-secret"}}},
        {
            "TosMountConfig": {
                "EnableTos": True,
                "MountPoints": [{"BucketName": {"SecretAccessKey": "response-secret"}}],
            }
        },
        {"TosMountConfig": ["response-secret"]},
    ],
)
def test_malformed_mount_detail_does_not_echo_secret_values(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(RuntimeArtifactError) as error:
        read_runtime_artifact_detail(_RawClient(payload), "r-one")
    assert error.value.status_code == 502
    assert "response-secret" not in str(error.value)
    assert error.value.__suppress_context__


def test_runtime_without_mount_has_no_storage_metadata() -> None:
    assert read_runtime_artifact_detail(
        _RawClient({"EnvironmentVariables": [{"Value": "secret"}]}), "r-one"
    ) == {"TosMountConfig": None}


def test_ownership_and_mount_use_one_response_without_exposing_tags() -> None:
    client = _RawClient(
        {
            "Tags": [{"Key": "veadk:owner", "Value": "alice"}],
            "TosMountConfig": {"EnableTos": True},
        }
    )
    seen: list[dict[str, str]] = []
    detail = read_runtime_artifact_detail(client, "r-one", authorize_tags=seen.append)
    assert seen == [{"veadk:owner": "alice"}]
    assert len(client.requests) == 1
    assert "Tags" not in detail
    assert detail["TosMountConfig"]["EnableTos"] is True


def test_denied_runtime_never_returns_mount_metadata() -> None:
    def deny(tags: dict[str, str]) -> None:
        assert tags == {}
        raise HTTPException(404, "Runtime not found")

    with pytest.raises(HTTPException) as error:
        read_runtime_artifact_detail(
            _RawClient({"Tags": None, "TosMountConfig": {"EnableTos": True}}),
            "r-private",
            authorize_tags=deny,
        )
    assert error.value.status_code == 404


@pytest.mark.parametrize(
    "region",
    [
        "cn-beijing.evil.example",
        "cn-beijing@evil.example",
        "cn-beijing/other",
        "cn-beijing:443",
        "cn-beijing?host=evil",
    ],
)
def test_region_cannot_inject_a_host_or_path_before_authorization(region: str) -> None:
    calls: list[str] = []
    app = FastAPI()

    def resolve(*args: Any) -> RuntimeArtifactAccess:
        calls.append("resolve")
        raise AssertionError("Invalid region must be rejected before the resolver")

    mount_routes(app, RuntimeArtifactService(lambda *_: None), resolve)
    client = TestClient(app)
    params = {"region": region, "appName": "agent"}
    assert (
        client.get(
            "/web/runtime-artifacts/r-one/sessions/s-one", params=params
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/web/runtime-artifacts/r-one/sessions/s-one/content/a.html", params=params
        ).status_code
        == 422
    )
    assert calls == []
