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

from typing import Any

import pytest


def test_viking_knowledgebase_search_passes_resource_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.knowledgebase.backends.vikingdb_knowledge_backend import (
        VikingDBKnowledgeBackend,
    )

    captured: dict[str, Any] = {}

    class _FakeVikingKnowledgeService:
        def __init__(self, **_: Any) -> None:
            pass

        def search_knowledge(self, **kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {"rewrite_query": None, "result_list": []}

    monkeypatch.setattr(
        VikingDBKnowledgeBackend,
        "model_post_init",
        lambda self, __context: None,
    )
    monkeypatch.setattr(
        "veadk.knowledgebase.backends.vikingdb_knowledge_backend."
        "VikingKnowledgeBaseService",
        _FakeVikingKnowledgeService,
    )

    backend = VikingDBKnowledgeBackend(
        index="vikingkl_we4191n",
        resource_id="kb-yef-example-we",
        volcengine_access_key="ak",
        volcengine_secret_key="sk",
    )

    backend.search("hello")

    assert captured["collection_name"] == "vikingkl_we4191n"
    assert captured["resource_id"] == "kb-yef-example-we"


def test_viking_knowledgebase_reads_byteplus_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.knowledgebase.backends.vikingdb_knowledge_backend import (
        VikingDBKnowledgeBackend,
    )

    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "bp-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "bp-sk")
    monkeypatch.setenv("BYTEPLUS_SESSION_TOKEN", "bp-token")
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "volc-ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "volc-sk")
    monkeypatch.setattr(
        VikingDBKnowledgeBackend,
        "model_post_init",
        lambda self, __context: None,
    )

    backend = VikingDBKnowledgeBackend(index="vikingkl_we4191n")

    assert backend.volcengine_access_key == "bp-ak"
    assert backend.volcengine_secret_key == "bp-sk"
    assert backend.session_token == "bp-token"


def test_byteplus_viking_knowledgebase_uses_byteplus_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.knowledgebase.backends.vikingdb_knowledge_backend import (
        VikingDBKnowledgeBackend,
    )

    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("DATABASE_VIKING_REGION", "cn-beijing")
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "bp-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "bp-sk")
    monkeypatch.setattr(
        VikingDBKnowledgeBackend,
        "collection_status",
        lambda self: {"existed": True},
    )

    backend = VikingDBKnowledgeBackend(index="vikingkl_we4191n")

    assert backend.region == "ap-southeast-1"
    assert backend.host == "api-knowledgebase.mlp.ap-southeast-1.bytepluses.com"
    assert (
        backend.base_url
        == "https://api-knowledgebase.mlp.ap-southeast-1.bytepluses.com"
    )
