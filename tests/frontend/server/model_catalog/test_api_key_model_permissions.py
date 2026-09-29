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

from typing import Any, cast

import pytest

from frontend.server.model_catalog.client import ModelApiKeyClient, ModelCatalogClient
from frontend.server.model_catalog.protocol import Provider
from frontend.server.model_catalog.models import (
    ModelApiKeyModelAccess,
    ModelApiKeyOption,
    ModelOption,
    ModelOptionsResponse,
)
from frontend.server.model_catalog.service import (
    ModelApiKeyService,
    ModelCatalogService,
    apply_api_key_permissions,
    build_model_permission_catalog,
    join_model_options,
)


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
def test_granted_video_and_shutdown_models_remain_visible_in_permission_summary(
    provider,
):
    raw_models = [
        {
            "id": "video-1",
            "name": "video",
            "domain": "VideoGeneration",
            "status": "Retiring",
        },
        {
            "id": "lite-1",
            "name": "lite",
            "domain": "VLM",
            "status": "Shutdown",
            "task_type": ["TextGeneration"],
        },
        {
            "id": "code-1",
            "name": "code",
            "domain": "VLM",
            "status": "Retiring",
            "task_type": ["TextGeneration"],
        },
    ]
    activations = [{"FoundationModelName": "code", "State": "Available"}]
    response = ModelOptionsResponse(
        provider=provider,
        models=join_model_options(activations, raw_models),
        model_permission_catalog=build_model_permission_catalog(
            activations, raw_models
        ),
    )
    key = ModelApiKeyOption(
        id="key",
        name="key",
        allow_all=False,
        model_access=ModelApiKeyModelAccess(
            effect="allow",
            all_models=False,
            model_ids=["video", "lite", "code", "missing"],
        ),
    )
    result = apply_api_key_permissions(response, key)
    assert result.api_key_model_permissions is not None
    assert [(item.name, item.state) for item in result.api_key_model_permissions] == [
        ("video", "VideoGeneration"),
        ("lite", "Shutdown"),
        ("code", "Available"),
        ("missing", "Unknown"),
    ]
    assert [model.name for model in result.models] == ["code"]
    assert "modelPermissionCatalog" not in result.model_dump(by_alias=True)


def test_granted_family_uses_an_active_version_when_an_older_version_is_shutdown():
    catalog = build_model_permission_catalog(
        [{"FoundationModelName": "code", "State": "Available"}],
        [
            {"id": "code-old", "name": "code", "domain": "LLM", "status": "Shutdown"},
            {"id": "code-new", "name": "code", "domain": "LLM", "status": "Running"},
        ],
    )
    assert catalog["code"].state == "Available"
    assert catalog["code-old"].state == "Shutdown"


@pytest.mark.parametrize(
    ("allow_all", "rule", "expected"),
    [
        (True, None, [True, True]),
        (False, {"effect": "allow", "all_models": True, "model_ids": []}, [True, True]),
        (
            False,
            {"effect": "allow", "all_models": False, "model_ids": ["seed-lite"]},
            [True, False],
        ),
        (
            False,
            {"effect": "allow", "all_models": False, "model_ids": ["seed-lite-260101"]},
            [True, False],
        ),
        (
            False,
            {"effect": "deny", "all_models": False, "model_ids": ["seed-pro"]},
            [True, False],
        ),
        (
            False,
            {"effect": "deny", "all_models": True, "model_ids": []},
            [False, False],
        ),
        (False, None, [False, False]),
    ],
)
def test_model_permissions_match_model_names_and_versions(
    allow_all: bool, rule: dict[str, Any] | None, expected: list[bool]
) -> None:
    models = [
        ModelOption(
            id=f"{name}-260101",
            name=name,
            display_name=name,
            vendor_name="",
            activation_state="Available",
            lifecycle_status="Retiring",
            available=True,
        )
        for name in ["seed-lite", "seed-pro"]
    ]
    response = ModelOptionsResponse(provider="volcengine", models=models)
    key = ModelApiKeyOption(
        id="key",
        name="key",
        allow_all=allow_all,
        model_access=ModelApiKeyModelAccess.model_validate(rule)
        if rule is not None
        else None,
    )
    result = apply_api_key_permissions(response, key)
    by_id = {model.id: model for model in result.models}
    assert [by_id[model.id].api_key_allowed for model in models] == expected
    assert [by_id[model.id].available for model in models] == expected
    assert all(model.available for model in response.models)
    assert "modelAccess" not in key.model_dump(by_alias=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
async def test_current_permissions_are_applied_even_when_model_catalog_is_cached(
    provider: Provider,
) -> None:
    class Keys:
        allow_all = True

        async def list_keys(self):
            return [
                {
                    "id": "key",
                    "name": "key",
                    "status": "Active",
                    "allow_all": self.allow_all,
                }
            ]

        async def get_raw_key(self, key_id):
            return "test-only-key"

    class Models:
        calls = 0

        async def list_models(self, **kwargs):
            self.calls += 1
            return [{"id": "seed-lite-260101", "name": "seed-lite", "domain": "LLM"}]

        async def list_activations(self):
            return [{"FoundationModelName": "seed-lite", "State": "Available"}]

    keys = Keys()
    models = Models()
    service = ModelCatalogService(
        provider=provider,
        client=cast(ModelCatalogClient, models),
        api_keys=ModelApiKeyService(
            provider=provider, client=cast(ModelApiKeyClient, keys)
        ),
    )
    first = await service.list_options(api_key_id="key")
    assert first.models[0].api_key_allowed is True
    keys.allow_all = False
    second = await service.list_options(api_key_id="key")
    assert second.models[0].api_key_allowed is False
    assert second.models[0].available is False
    assert models.calls == 1
    keys.allow_all = True
    third = await service.list_options(api_key_id="key")
    assert third.models[0].available is True
