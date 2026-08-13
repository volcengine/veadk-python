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

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from frontend.server.model_catalog.client import (
    PROVIDER_CONFIGS,
    ModelApiKeyClient,
    ModelCatalogError,
)
from frontend.server.model_catalog.models import ModelOption, ModelOptionsResponse
from frontend.server.model_catalog.routes import (
    build_model_catalog_service,
    mount_model_catalog_routes,
)
from frontend.server.model_catalog.service import (
    ModelApiKeyService,
    ModelCatalogService,
    join_model_options,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "expected_models_url", "expected_openapi_host"),
    [
        (
            "volcengine",
            "https://ark.cn-beijing.volces.com/api/v3/models",
            "open.volcengineapi.com",
        ),
        (
            "byteplus",
            "https://ark.ap-southeast.bytepluses.com/api/v3/models",
            "open.byteplusapi.com",
        ),
    ],
)
async def test_provider_urls_and_explicit_model_key(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    expected_models_url: str,
    expected_openapi_host: str,
) -> None:
    monkeypatch.setenv("MODEL_AGENT_API_KEY", "explicit-model-key")
    seen_openapi: list[dict[str, Any]] = []

    def model_api(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == expected_models_url
        assert request.headers["authorization"] == "Bearer selected-model-key"
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {
                        "id": "seed-pro-260101",
                        "name": "seed-pro",
                        "domain": "LLM",
                        "task_type": ["TextGeneration"],
                    }
                ],
            },
        )

    def signed_request(**kwargs: Any) -> dict[str, Any]:
        seen_openapi.append(kwargs)
        action = kwargs["query"]["Action"]
        if action == "ListApiKeys":
            return {
                "Result": {
                    "TotalCount": 1,
                    "Items": [{"Id": "key-1", "Name": "first-key"}],
                }
            }
        if action == "GetRawApiKey":
            assert kwargs["request_body"]["ProjectName"] == "default"
            return {"Result": {"ApiKey": "selected-model-key"}}
        return {
            "ResponseMetadata": {"RequestId": "request-id"},
            "Result": {
                "TotalCount": 1,
                "Items": [
                    {
                        "FoundationModelName": "seed-pro",
                        "State": "Available",
                        "DisplayName": "Seed Pro",
                        "VendorName": "ByteDance",
                    }
                ],
            },
        }

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(model_api))
    service = build_model_catalog_service(
        provider=provider,  # type: ignore[arg-type]
        resolve_credentials=lambda: ("ak", "sk", "sts"),
        http_client=http_client,
        token_loader=lambda *args, **kwargs: pytest.fail(
            "selected key is resolved by ID"
        ),
        signed_request=signed_request,
    )
    try:
        result = await service.list_options()
    finally:
        await http_client.aclose()

    assert result.models[0].id == "seed-pro-260101"
    assert result.selected_api_key_id == "key-1"
    assert all(call["host"] == expected_openapi_host for call in seen_openapi)
    activation_call = next(
        call
        for call in seen_openapi
        if call["query"]["Action"] == "ListModelActivations"
    )
    assert activation_call["query"] == {
        "Action": "ListModelActivations",
        "Version": "2024-01-01",
    }
    assert activation_call["request_body"]["Filter"] == {"FoundationModelDomain": "LLM"}
    assert activation_call["request_body"]["WithPrice"] is False
    assert activation_call["request_body"]["WithFreeUsage"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "expected_host"),
    [
        ("volcengine", "open.volcengineapi.com"),
        ("byteplus", "open.byteplusapi.com"),
    ],
)
async def test_api_key_catalog_paginates_in_request_body(
    provider: str,
    expected_host: str,
) -> None:
    seen_pages: list[int] = []
    seen_hosts: list[str] = []

    def signed_request(**kwargs: Any) -> dict[str, Any]:
        seen_hosts.append(kwargs["host"])
        page = kwargs["request_body"]["PageNumber"]
        seen_pages.append(page)
        return {
            "Result": {
                "PageNumber": page,
                "TotalCount": 11,
                "Items": [
                    {"Id": f"key-{page}-{index}", "Name": f"name-{page}-{index}"}
                    for index in range(10 if page == 1 else 1)
                ],
            }
        }

    client = ModelApiKeyClient(
        config=PROVIDER_CONFIGS[provider],  # type: ignore[index]
        resolve_credentials=lambda: ("ak", "sk", None),
        signed_request=signed_request,
    )

    keys = await client.list_keys()

    assert seen_pages == [1, 2]
    assert seen_hosts == [expected_host, expected_host]
    assert len(keys) == 11


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "expected_host"),
    [
        ("volcengine", "open.volcengineapi.com"),
        ("byteplus", "open.byteplusapi.com"),
    ],
)
async def test_raw_api_key_preserves_numeric_control_plane_id(
    provider: str,
    expected_host: str,
) -> None:
    request_body: dict[str, Any] = {}
    request_host = ""

    def signed_request(**kwargs: Any) -> dict[str, Any]:
        nonlocal request_host
        request_host = kwargs["host"]
        request_body.update(kwargs["request_body"])
        return {"Result": {"ApiKey": "selected-model-key"}}

    client = ModelApiKeyClient(
        config=PROVIDER_CONFIGS[provider],  # type: ignore[index]
        resolve_credentials=lambda: ("ak", "sk", None),
        signed_request=signed_request,
    )

    assert await client.get_raw_key("4028965") == "selected-model-key"
    assert request_host == expected_host
    assert request_body == {"Id": 4028965, "ProjectName": "default"}


@pytest.mark.asyncio
async def test_activation_catalog_is_fetched_across_all_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_AGENT_API_KEY", "explicit-model-key")
    pages: list[int] = []

    def signed_request(**kwargs: Any) -> dict[str, Any]:
        action = kwargs["query"]["Action"]
        if action == "ListApiKeys":
            return {
                "Result": {
                    "TotalCount": 1,
                    "Items": [{"Id": "key-1", "Name": "first-key"}],
                }
            }
        if action == "GetRawApiKey":
            assert kwargs["request_body"]["ProjectName"] == "default"
            return {"Result": {"ApiKey": "explicit-model-key"}}
        page = kwargs["request_body"]["PageNumber"]
        pages.append(page)
        count = 100 if page == 1 else 1
        return {
            "Result": {
                "TotalCount": 101,
                "Items": [
                    {
                        "FoundationModelName": f"model-{page}-{index}",
                        "State": "Available",
                    }
                    for index in range(count)
                ],
            }
        }

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"data": []}))
    )
    service = build_model_catalog_service(
        provider="volcengine",
        resolve_credentials=lambda: ("ak", "sk", None),
        http_client=http_client,
        signed_request=signed_request,
    )
    try:
        await service.list_options()
    finally:
        await http_client.aclose()

    assert pages == [1, 2]


def test_join_filters_and_marks_lifecycle_and_activation_states() -> None:
    activations = [
        {
            "FoundationModelName": "active",
            "State": "Available",
            "DisplayName": "Active Model",
            "VendorName": "Vendor A",
        },
        {
            "FoundationModelName": "closed",
            "State": "Unavailable",
            "DisplayName": "Closed Model",
            "VendorName": "Vendor B",
        },
        {
            "FoundationModelName": "retiring",
            "State": "Available",
            "DisplayName": "Retiring Model",
            "VendorName": "Vendor C",
        },
    ]
    models = [
        {
            "id": "active-260101",
            "name": "active",
            "domain": "LLM",
            "task_type": ["TextGeneration"],
        },
        {
            "id": "closed-260101",
            "name": "closed",
            "status": "Running",
            "domain": "VLM",
            "task_type": ["TextGeneration", "VisualQuestionAnswering"],
        },
        {
            "id": "retiring-250101",
            "name": "retiring",
            "status": "Retiring",
            "domain": "LLM",
            "task_type": ["TextGeneration"],
        },
        {
            "id": "shutdown-240101",
            "name": "active",
            "status": "Shutdown",
            "domain": "LLM",
            "task_type": ["TextGeneration"],
        },
        {
            "id": "image-260101",
            "name": "active",
            "domain": "ImageGeneration",
            "task_type": ["TextToImage"],
        },
        {
            "id": "embedding-260101",
            "name": "active",
            "domain": "LLM",
            "task_type": ["TextEmbedding"],
        },
        {
            "id": "not-in-activation-list-260101",
            "name": "not-in-activation-list",
            "domain": "LLM",
            "task_type": ["TextGeneration"],
        },
    ]

    options = join_model_options(activations, models)

    assert [item.id for item in options] == [
        "active-260101",
        "retiring-250101",
        "closed-260101",
        "not-in-activation-list-260101",
    ]
    assert options[0].lifecycle_status == "Running"
    assert options[0].available is True
    assert options[1].lifecycle_status == "Retiring"
    assert options[1].available is True
    assert options[2].activation_state == "Unavailable"
    assert options[2].available is False
    assert options[3].activation_state == "Unavailable"
    assert options[3].display_name == "not-in-activation-list"
    assert options[3].vendor_name == ""
    assert options[3].available is False


@pytest.mark.asyncio
async def test_route_uses_camel_case_response() -> None:
    response = ModelOptionsResponse(
        provider="volcengine",
        models=[
            ModelOption(
                id="doubao-seed-2-1-pro-260628",
                name="doubao-seed-2-1-pro",
                display_name="Doubao Seed 2.1 Pro",
                vendor_name="ByteDance",
                activation_state="Available",
                lifecycle_status="Running",
                available=True,
            )
        ],
    )
    app = FastAPI()
    mount_model_catalog_routes(
        app,
        service=SimpleNamespace(  # type: ignore[arg-type]
            list_options=lambda: _async_value(response)
        ),
        authorize=lambda _: None,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        result = await client.get("/web/model-options")

    assert result.status_code == 200
    assert result.json() == {
        "provider": "volcengine",
        "models": [
            {
                "id": "doubao-seed-2-1-pro-260628",
                "name": "doubao-seed-2-1-pro",
                "displayName": "Doubao Seed 2.1 Pro",
                "vendorName": "ByteDance",
                "activationState": "Available",
                "lifecycleStatus": "Running",
                "available": True,
            }
        ],
    }


@pytest.mark.asyncio
async def test_route_returns_sanitized_retryable_upstream_error() -> None:
    async def fail() -> ModelOptionsResponse:
        raise ModelCatalogError(
            "云账号凭据不可用，请检查 Studio 的云账号配置后重试。",
            status_code=503,
        )

    app = FastAPI()
    mount_model_catalog_routes(
        app,
        service=SimpleNamespace(list_options=fail),  # type: ignore[arg-type]
        authorize=lambda _: None,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/web/model-options")

    assert response.status_code == 503
    assert "重试" in response.json()["detail"]


@pytest.mark.asyncio
async def test_non_json_model_response_does_not_leak_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_AGENT_API_KEY", "secret-model-token")

    def signed_request(**kwargs: Any) -> dict[str, Any]:
        raise RuntimeError(f"upstream rejected {kwargs['ak']}")

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, text="secret-model-token is invalid")
        )
    )
    service = build_model_catalog_service(
        provider="volcengine",
        resolve_credentials=lambda: ("secret-access-key", "secret-key", None),
        http_client=http_client,
        signed_request=signed_request,
    )
    try:
        with pytest.raises(ModelCatalogError) as raised:
            await service.list_options()
    finally:
        await http_client.aclose()

    message = str(raised.value)
    assert "重试" in message
    assert "secret-access-key" not in message
    assert "secret-model-token" not in message


@pytest.mark.asyncio
async def test_empty_api_key_catalog_has_actionable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MODEL_AGENT_API_KEY", raising=False)

    service = build_model_catalog_service(
        provider="volcengine",
        resolve_credentials=lambda: ("secret-access-key", "secret-key", None),
        signed_request=lambda **_: {"Result": {"TotalCount": 0, "Items": []}},
    )

    with pytest.raises(ModelCatalogError) as raised:
        await service.list_options()

    assert raised.value.status_code == 404
    assert "API Key" in str(raised.value)
    assert "secret-access-key" not in str(raised.value)


@pytest.mark.asyncio
async def test_cache_serves_stale_catalog_when_refresh_fails() -> None:
    now = {"value": 0.0}

    class FakeClient:
        calls = 0

        async def list_activations(self) -> list[dict[str, Any]]:
            self.calls += 1
            if self.calls > 1:
                raise ModelCatalogError("temporary failure")
            return [
                {
                    "FoundationModelName": "seed-pro",
                    "State": "Available",
                    "DisplayName": "Seed Pro",
                }
            ]

        async def list_models(self) -> list[dict[str, Any]]:
            return [
                {
                    "id": "seed-pro-260101",
                    "name": "seed-pro",
                    "domain": "LLM",
                    "task_type": ["TextGeneration"],
                }
            ]

    client = FakeClient()
    service = ModelCatalogService(
        provider="volcengine",
        client=client,  # type: ignore[arg-type]
        ttl_seconds=300,
        clock=lambda: now["value"],
    )
    first = await service.list_options()
    cached = await service.list_options()
    now["value"] = 301
    stale = await service.list_options()

    assert client.calls == 2
    assert first is cached
    assert stale is first


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "expected_host"),
    [
        ("volcengine", "open.volcengineapi.com"),
        ("byteplus", "open.byteplusapi.com"),
    ],
)
async def test_api_key_routes_are_safe_key_scoped_and_force_refresh(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    expected_host: str,
) -> None:
    monkeypatch.delenv("MODEL_AGENT_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_AGENT_API_KEY_NAME", raising=False)
    calls = {"list_keys": 0, "raw": 0, "activations": 0, "models": 0}
    authorizations: list[str] = []
    openapi_hosts: list[str] = []

    def signed_request(**kwargs: Any) -> dict[str, Any]:
        openapi_hosts.append(kwargs["host"])
        action = kwargs["query"]["Action"]
        if action == "ListApiKeys":
            calls["list_keys"] += 1
            return {
                "Result": {
                    "TotalCount": 2,
                    "Items": [
                        {
                            "Id": "key-1",
                            "Name": "first-key",
                            "ApiKey": "must-not-leak",
                        },
                        {"Id": "key-2", "Name": "second-key"},
                    ],
                }
            }
        if action == "GetRawApiKey":
            calls["raw"] += 1
            assert kwargs["request_body"]["ProjectName"] == "default"
            key_id = kwargs["request_body"]["Id"]
            return {"Result": {"ApiKey": f"raw-{key_id}"}}
        calls["activations"] += 1
        return {
            "Result": {
                "TotalCount": 1,
                "Items": [
                    {
                        "FoundationModelName": "seed-pro",
                        "State": "Available",
                        "DisplayName": "Seed Pro",
                    }
                ],
            }
        }

    def model_api(request: httpx.Request) -> httpx.Response:
        calls["models"] += 1
        authorizations.append(request.headers["authorization"])
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "seed-pro-260101",
                        "name": "seed-pro",
                        "domain": "LLM",
                        "task_type": ["TextGeneration"],
                    }
                ]
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(model_api))
    service = build_model_catalog_service(
        provider=provider,  # type: ignore[arg-type]
        resolve_credentials=lambda: ("access-key", "secret-key", None),
        http_client=http_client,
        token_loader=lambda *_, **__: pytest.fail("raw key is resolved by selected ID"),
        signed_request=signed_request,
    )
    app = FastAPI()
    mount_model_catalog_routes(app, service=service, authorize=lambda _: None)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            keys_response = await client.get("/web/model-api-keys")
            first = await client.get("/web/model-options?apiKeyId=key-2")
            cached = await client.get("/web/model-options?apiKeyId=key-2")
            refreshed = await client.get(
                "/web/model-options?apiKeyId=key-2&refresh=true"
            )
    finally:
        await http_client.aclose()

    assert keys_response.status_code == 200
    assert keys_response.json() == {
        "provider": provider,
        "keys": [
            {"id": "key-1", "name": "first-key"},
            {"id": "key-2", "name": "second-key"},
        ],
        "defaultKeyId": "key-1",
    }
    assert "must-not-leak" not in keys_response.text
    assert "raw-key-2" not in keys_response.text
    assert first.json()["selectedApiKeyId"] == "key-2"
    assert cached.json() == first.json()
    assert refreshed.json()["selectedApiKeyId"] == "key-2"
    assert calls == {
        "list_keys": 2,
        "raw": 2,
        "activations": 2,
        "models": 2,
    }
    assert authorizations == ["Bearer raw-key-2", "Bearer raw-key-2"]
    assert openapi_hosts
    assert set(openapi_hosts) == {expected_host}


@pytest.mark.asyncio
async def test_unknown_key_id_is_rejected_before_raw_key_lookup() -> None:
    class FakeApiKeyClient:
        raw_calls = 0

        async def list_keys(self) -> list[dict[str, str]]:
            return [{"id": "known", "name": "known-key"}]

        async def get_raw_key(self, key_id: str) -> str:
            self.raw_calls += 1
            return f"raw-{key_id}"

    api_key_client = FakeApiKeyClient()
    api_keys = ModelApiKeyService(
        provider="byteplus",
        client=api_key_client,  # type: ignore[arg-type]
    )
    catalog = await api_keys.list_keys()

    with pytest.raises(ModelCatalogError) as raised:
        await api_keys.resolve_raw_key("unknown", known_keys=catalog)

    assert raised.value.status_code == 404
    assert api_key_client.raw_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
async def test_api_key_value_route_returns_selected_value_without_caching(
    provider: str,
) -> None:
    class FakeApiKeyClient:
        raw_calls = 0

        async def list_keys(self) -> list[dict[str, str]]:
            return [{"id": "known-key-id", "name": "known-key"}]

        async def get_raw_key(self, key_id: str) -> str:
            self.raw_calls += 1
            assert key_id == "known-key-id"
            return "raw-secret-value"

    api_key_client = FakeApiKeyClient()
    service = ModelCatalogService(
        provider=provider,  # type: ignore[arg-type]
        client=SimpleNamespace(),  # type: ignore[arg-type]
        api_keys=ModelApiKeyService(
            provider="volcengine",
            client=api_key_client,  # type: ignore[arg-type]
        ),
    )
    app = FastAPI()
    mount_model_catalog_routes(app, service=service, authorize=lambda _: None)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/web/model-api-keys/known-key-id/value")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"value": "raw-secret-value"}
    assert api_key_client.raw_calls == 1


@pytest.mark.asyncio
async def test_api_key_value_route_rejects_unknown_id_without_leaking_values() -> None:
    class FakeApiKeyClient:
        raw_calls = 0

        async def list_keys(self) -> list[dict[str, str]]:
            return [{"id": "known-key-id", "name": "known-key"}]

        async def get_raw_key(self, key_id: str) -> str:
            self.raw_calls += 1
            return "raw-secret-that-must-not-leak"

    api_key_client = FakeApiKeyClient()
    service = ModelCatalogService(
        provider="volcengine",
        client=SimpleNamespace(),  # type: ignore[arg-type]
        api_keys=ModelApiKeyService(
            provider="volcengine",
            client=api_key_client,  # type: ignore[arg-type]
        ),
    )
    app = FastAPI()
    mount_model_catalog_routes(app, service=service, authorize=lambda _: None)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/web/model-api-keys/unknown/value")

    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"
    assert "raw-secret-that-must-not-leak" not in response.text
    assert "不存在" in response.json()["detail"]
    assert api_key_client.raw_calls == 0


@pytest.mark.asyncio
async def test_api_key_value_route_sanitizes_unexpected_upstream_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    leaked_value = "raw-secret-from-upstream"

    async def fail(_: str) -> str:
        raise RuntimeError(f"upstream returned {leaked_value}")

    app = FastAPI()
    mount_model_catalog_routes(
        app,
        service=SimpleNamespace(resolve_raw_key=fail),  # type: ignore[arg-type]
        authorize=lambda _: None,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/web/model-api-keys/known-key-id/value")

    assert response.status_code == 502
    assert response.headers["cache-control"] == "no-store"
    assert "重试" in response.json()["detail"]
    assert leaked_value not in response.text
    assert leaked_value not in caplog.text


async def _async_value(value: Any) -> Any:
    return value
