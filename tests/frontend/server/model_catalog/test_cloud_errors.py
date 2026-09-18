# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import httpx
import pytest
import requests
from fastapi import FastAPI

from frontend.server.model_catalog.client import PROVIDER_CONFIGS, ModelCatalogClient
from frontend.server.model_catalog.routes import mount_model_catalog_routes
from frontend.server.model_catalog.service import ModelCatalogService
from frontend.server.video.client import ArkHttpClient


def test_model_catalog_routes_keep_network_clients_lazy():
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import frontend.server.model_catalog.routes; "
            "assert 'requests' not in sys.modules; "
            "assert 'frontend.server.video.client' not in sys.modules; "
            "assert 'veadk.utils.volcengine_sign' not in sys.modules",
        ],
        cwd=Path(__file__).resolve().parents[4],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
@pytest.mark.parametrize("status", [403, 429, 503])
async def test_activation_errors_preserve_cloud_status_and_exact_body(provider, status):
    body = '{\n  "ResponseMetadata": {"RequestId": "cloud-request-id", "Error": {"Code": "CloudFailure", "Message": "original cloud message"}}\n}'

    def signed_request(**kwargs):
        assert kwargs["response_type"] == "response"
        response = requests.Response()
        response.status_code = status
        response._content = body.encode()
        response.headers["X-Request-Id"] = "cloud-request-id"
        response.raise_for_status()

    catalog = ModelCatalogClient(
        config=PROVIDER_CONFIGS[provider],
        resolve_credentials=lambda: ("test-ak", "test-sk", None),
        ark_http_client=cast(ArkHttpClient, SimpleNamespace()),
        signed_request=signed_request,
    )

    async def list_options():
        await catalog.list_activations()

    app = FastAPI()
    mount_model_catalog_routes(
        app,
        service=cast(ModelCatalogService, SimpleNamespace(list_options=list_options)),
        authorize=lambda _: None,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/web/model-options")
    assert response.status_code == status
    assert response.text == body
    assert response.headers["x-request-id"] == "cloud-request-id"
    assert response.headers["x-studio-error-source"] == "upstream"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_timeout_is_identified_as_no_cloud_response():
    def signed_request(**kwargs):
        raise requests.Timeout("cloud connection timed out")

    catalog = ModelCatalogClient(
        config=PROVIDER_CONFIGS["volcengine"],
        resolve_credentials=lambda: ("test-ak", "test-sk", None),
        ark_http_client=cast(ArkHttpClient, SimpleNamespace()),
        signed_request=signed_request,
    )

    async def list_options():
        await catalog.list_activations()

    app = FastAPI()
    mount_model_catalog_routes(
        app,
        service=cast(ModelCatalogService, SimpleNamespace(list_options=list_options)),
        authorize=lambda _: None,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/web/model-options")
    assert response.status_code == 504
    assert response.headers["x-studio-error-source"] == "transport"
    assert "未收到云服务响应" in response.json()["detail"]
    assert "权限" not in response.text
