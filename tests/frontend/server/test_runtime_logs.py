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

import base64
import json
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from frontend.server.runtime_logs import (
    RuntimeLogService,
    RuntimeRequestContext,
    console_runtime_url,
    mount_runtime_log_routes,
    runtime_request_context,
    studio_runtime_context_headers,
)


def _encoded_session_header(instance_name: str) -> str:
    payload = json.dumps({"x-faas-instance-name": instance_name}).encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    return f"v1.{encoded}.signature"


def test_runtime_request_context_extracts_only_safe_headers() -> None:
    context = runtime_request_context(
        {
            "x-faas-request-id": "request-123",
            "x-session-id": _encoded_session_header("instance-abc"),
            "authorization": "Bearer secret",
        }
    )

    assert context == RuntimeRequestContext(
        instance_name="instance-abc",
        request_id="request-123",
    )
    assert studio_runtime_context_headers(context) == {
        "X-Studio-FaaS-Instance": "instance-abc",
        "X-Studio-FaaS-Request-Id": "request-123",
        "Cache-Control": "no-store",
    }


@pytest.mark.parametrize(
    ("provider", "expected_origin"),
    [
        ("volcengine", "https://console.volcengine.com"),
        ("byteplus", "https://console.byteplus.com"),
    ],
)
def test_console_runtime_url_supports_both_providers(
    provider: str,
    expected_origin: str,
) -> None:
    url = console_runtime_url(
        provider=provider,
        region="ap-southeast-1" if provider == "byteplus" else "cn-beijing",
        project_name="project with spaces",
        runtime_id="runtime/1",
        instance_name="instance/1",
    )

    assert url.startswith(f"{expected_origin}/agentkit/region:agentkit+")
    assert "projectName=project+with+spaces" in url
    assert "runtimeId=runtime%2F1" in url
    assert "instanceName=instance%2F1" in url


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "region"),
    [
        ("volcengine", "cn-beijing"),
        ("byteplus", "ap-southeast-1"),
    ],
)
async def test_runtime_log_service_validates_instance_and_reads_logs(
    provider: str,
    region: str,
) -> None:
    calls: list[tuple[str, Any]] = []

    class _Client:
        def list_runtime_instances(self, request: Any) -> SimpleNamespace:
            calls.append(("list", request))
            return SimpleNamespace(
                instance_items=[
                    SimpleNamespace(
                        instance_name="instance-abc",
                        runtime_id="runtime-1",
                    )
                ]
            )

        def get_runtime_instance_logs(self, request: Any) -> SimpleNamespace:
            calls.append(("logs", request))
            return SimpleNamespace(logs="INFO ready\nERROR failed")

    clients: list[tuple[str, str, str, str]] = []

    def create_client(
        *, access_key: str, secret_key: str, session_token: str, region: str
    ) -> _Client:
        clients.append((access_key, secret_key, session_token, region))
        return _Client()

    service = RuntimeLogService(
        provider=provider,
        resolve_credentials=lambda: ("ak", "sk", "token"),
        create_client=create_client,
        sanitize=lambda value: value.replace("failed", "***"),
    )

    snapshot = await service.snapshot(
        runtime_id="runtime-1",
        instance_name="instance-abc",
        region=region,
    )

    assert snapshot == "INFO ready\nERROR ***"
    assert clients == [("ak", "sk", "token", region)]
    assert calls[0][0] == "list"
    assert calls[0][1].runtime_id == "runtime-1"
    assert calls[1][0] == "logs"
    assert calls[1][1].instance_name == "instance-abc"
    assert calls[1][1].runtime_id == "runtime-1"


@pytest.mark.asyncio
async def test_runtime_log_service_rejects_an_instance_outside_runtime() -> None:
    class _Client:
        def list_runtime_instances(self, request: Any) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                instance_items=[SimpleNamespace(instance_name="other-instance")]
            )

    service = RuntimeLogService(
        provider="volcengine",
        resolve_credentials=lambda: ("ak", "sk", ""),
        create_client=lambda **kwargs: _Client(),
    )

    with pytest.raises(ValueError, match="instance_not_found"):
        await service.snapshot(
            runtime_id="runtime-1",
            instance_name="instance-abc",
            region="cn-beijing",
        )


@pytest.mark.asyncio
async def test_runtime_log_service_resolves_the_only_runtime_instance() -> None:
    class _Client:
        def list_runtime_instances(self, request: Any) -> SimpleNamespace:
            return SimpleNamespace(
                instance_items=[
                    SimpleNamespace(
                        instance_name="instance-abc",
                        runtime_id=request.runtime_id,
                    )
                ]
            )

    service = RuntimeLogService(
        provider="volcengine",
        resolve_credentials=lambda: ("ak", "sk", ""),
        create_client=lambda **kwargs: _Client(),
    )

    assert (
        await service.resolve_instance(
            _Client(),
            runtime_id="runtime-1",
            session_id="session-1",
        )
        == "instance-abc"
    )


@pytest.mark.asyncio
async def test_runtime_log_service_matches_session_across_scaled_instances() -> None:
    class _Client:
        def list_runtime_instances(self, request: Any) -> SimpleNamespace:
            return SimpleNamespace(
                instance_items=[
                    SimpleNamespace(
                        instance_name="instance-a", runtime_id=request.runtime_id
                    ),
                    SimpleNamespace(
                        instance_name="instance-b", runtime_id=request.runtime_id
                    ),
                ]
            )

        def get_runtime_instance_logs(self, request: Any) -> SimpleNamespace:
            logs = "INFO other session"
            if request.instance_name == "instance-b":
                logs = "INFO session-1 request"
            return SimpleNamespace(logs=logs)

    service = RuntimeLogService(
        provider="volcengine",
        resolve_credentials=lambda: ("ak", "sk", ""),
        create_client=lambda **kwargs: _Client(),
    )

    assert (
        await service.resolve_instance(
            _Client(),
            runtime_id="runtime-1",
            session_id="session-1",
        )
        == "instance-b"
    )


def test_runtime_log_route_authorizes_and_streams_one_snapshot() -> None:
    class _Client:
        def list_runtime_instances(self, request: Any) -> SimpleNamespace:
            return SimpleNamespace(
                instance_items=[
                    SimpleNamespace(
                        instance_name="instance-abc",
                        runtime_id=request.runtime_id,
                    )
                ]
            )

        def get_runtime_instance_logs(self, request: Any) -> SimpleNamespace:
            del request
            return SimpleNamespace(logs="INFO ready")

    app = FastAPI()
    authorized: list[tuple[str, str]] = []

    def authorize(_request: Any, runtime_id: str, region: str) -> SimpleNamespace:
        authorized.append((runtime_id, region))
        return SimpleNamespace(project_name="project-a")

    mount_runtime_log_routes(
        app,
        service=RuntimeLogService(
            provider="byteplus",
            resolve_credentials=lambda: ("ak", "sk", ""),
            create_client=lambda **kwargs: _Client(),
        ),
        authorize_runtime=authorize,
        normalize_region=lambda value: value or "ap-southeast-1",
        safe_error=lambda error: str(error),
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/runtime-logs/runtime-1/stream",
            params={
                "region": "ap-southeast-1",
                "session_id": "session-1",
                "follow": "false",
            },
        )

    assert response.status_code == 200
    assert authorized == [("runtime-1", "ap-southeast-1")]
    assert '"type":"context"' in response.text
    assert "https://console.byteplus.com/agentkit/" in response.text
    assert '"type":"logs","text":"INFO ready"' in response.text
    assert '"type":"done"' in response.text


def test_runtime_log_route_preserves_runtime_authorization_failure() -> None:
    app = FastAPI()
    mount_runtime_log_routes(
        app,
        service=RuntimeLogService(
            provider="volcengine",
            resolve_credentials=lambda: ("ak", "sk", ""),
        ),
        authorize_runtime=lambda request, runtime_id, region: (_ for _ in ()).throw(
            HTTPException(status_code=404, detail="runtime_access_denied")
        ),
        normalize_region=lambda value: value or "cn-beijing",
        safe_error=lambda error: str(error),
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/runtime-logs/runtime-1/stream",
            params={"instance_name": "instance-abc", "follow": "false"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "runtime_access_denied"}
