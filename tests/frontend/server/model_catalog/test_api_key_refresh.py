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

from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from frontend.server.model_catalog.client import PROVIDER_CONFIGS, ModelApiKeyClient
from frontend.server.model_catalog.protocol import ModelCatalogError, Provider
from frontend.server.model_catalog.routes import (
    build_model_catalog_service,
    mount_model_catalog_routes,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
async def test_page_reload_reads_created_updated_and_deleted_keys(
    provider: Provider,
) -> None:
    items: list[dict[str, Any]] = []
    calls = 0

    def request(**kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        assert kwargs["query"]["Action"] == "ListApiKeys"
        assert "Filter" not in kwargs["request_body"]
        assert kwargs["host"] == PROVIDER_CONFIGS[provider].openapi_host
        calls += 1
        return {"Result": {"TotalCount": len(items), "Items": list(items)}}

    service = build_model_catalog_service(
        provider=provider,
        resolve_credentials=lambda: ("test-ak", "test-sk", None),
        signed_request=request,
    )
    app = FastAPI()
    mount_model_catalog_routes(app, service=service, authorize=lambda _: None)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.get("/web/model-api-keys")
        assert first.json()["keys"] == []
        items.extend(
            [
                {
                    "Id": "disabled",
                    "Name": "A",
                    "Status": "Restricted",
                    "AccessControlInfo": {"AllowAll": False},
                    "Key": "never-expose",
                },
                {
                    "Id": "enabled",
                    "Name": "B",
                    "Status": "Active",
                    "AccessControlInfo": {"AllowAll": True},
                },
            ]
        )
        second = await client.get("/web/model-api-keys")
        assert second.headers["cache-control"] == "no-store"
        assert second.json()["keys"] == [
            {"id": "disabled", "name": "A", "status": "Restricted", "allowAll": False},
            {"id": "enabled", "name": "B", "status": "Active", "allowAll": True},
        ]
        assert second.json()["defaultKeyId"] == "enabled"
        assert "never-expose" not in second.text
        items[0]["Status"] = "Active"
        items.pop()
        third = await client.get("/web/model-api-keys?refresh=false")
        assert third.json()["keys"] == [
            {"id": "disabled", "name": "A", "status": "Active", "allowAll": False}
        ]
        assert calls == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
async def test_pagination_retains_duplicate_names_and_sorts_consistently(
    provider: Provider,
) -> None:
    pages: list[int] = []

    def request(**kwargs: Any) -> dict[str, Any]:
        page = kwargs["request_body"]["PageNumber"]
        pages.append(page)
        items = [
            [{"Id": "3", "Name": "Beta"}, {"Id": "2", "Name": "Alpha"}],
            [{"Id": "2", "Name": "Alpha"}, {"Id": "1", "Name": "Alpha"}],
            [{"Id": "4", "Name": "Gamma"}],
        ][page - 1]
        return {"Result": {"TotalCount": 4, "Items": items}}

    client = ModelApiKeyClient(
        config=PROVIDER_CONFIGS[provider],
        resolve_credentials=lambda: ("test-ak", "test-sk", None),
        signed_request=request,
    )
    result = await client.list_keys()
    assert [item["id"] for item in result] == ["1", "2", "3", "4"]
    assert pages == [1, 2, 3]


@pytest.mark.asyncio
async def test_incomplete_pagination_is_not_reported_as_a_complete_list() -> None:
    def request(**kwargs: Any) -> dict[str, Any]:
        items = (
            [{"Id": "1", "Name": "A"}]
            if kwargs["request_body"]["PageNumber"] == 1
            else []
        )
        return {"Result": {"TotalCount": 2, "Items": items}}

    client = ModelApiKeyClient(
        config=PROVIDER_CONFIGS["volcengine"],
        resolve_credentials=lambda: ("test-ak", "test-sk", None),
        signed_request=request,
    )
    with pytest.raises(ModelCatalogError):
        await client.list_keys()
