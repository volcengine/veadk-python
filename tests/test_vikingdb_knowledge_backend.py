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


def test_byteplus_viking_knowledgebase_uses_hong_kong_fallback(
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

    assert backend.region == "cn-hongkong"
    assert backend.host == "api-knowledgebase.mlp.cn-hongkong.bytepluses.com"
    assert (
        backend.base_url == "https://api-knowledgebase.mlp.cn-hongkong.bytepluses.com"
    )
    assert backend.tos_config.region == "cn-hongkong"
    assert backend.tos_config.endpoint == "tos-cn-hongkong.bytepluses.com"


def test_byteplus_viking_knowledgebase_keeps_hong_kong_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.knowledgebase.backends.vikingdb_knowledge_backend import (
        VikingDBKnowledgeBackend,
    )

    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("DATABASE_VIKING_REGION", "cn-hongkong")
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "bp-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "bp-sk")
    monkeypatch.setattr(
        VikingDBKnowledgeBackend,
        "collection_status",
        lambda self: {"existed": True},
    )

    backend = VikingDBKnowledgeBackend(index="vikingkl_we4191n")

    assert backend.region == "cn-hongkong"
    assert backend.host == "api-knowledgebase.mlp.cn-hongkong.bytepluses.com"
    assert (
        backend.base_url == "https://api-knowledgebase.mlp.cn-hongkong.bytepluses.com"
    )


def test_byteplus_viking_knowledgebase_keeps_explicit_tos_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.configs.database_configs import NormalTOSConfig
    from veadk.knowledgebase.backends.vikingdb_knowledge_backend import (
        VikingDBKnowledgeBackend,
    )

    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "bp-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "bp-sk")
    monkeypatch.setattr(
        VikingDBKnowledgeBackend,
        "collection_status",
        lambda self: {"existed": True},
    )

    tos_config = NormalTOSConfig(
        bucket="custom-bucket",
        endpoint="tos-ap-southeast-1.bytepluses.com",
        region="ap-southeast-1",
    )
    backend = VikingDBKnowledgeBackend(
        index="vikingkl_we4191n",
        tos_config=tos_config,
    )

    assert backend.region == "cn-hongkong"
    assert backend.tos_config.region == "ap-southeast-1"
    assert backend.tos_config.endpoint == "tos-ap-southeast-1.bytepluses.com"


def test_byteplus_viking_knowledgebase_keeps_explicit_tosconfig(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.configs.database_configs import TOSConfig
    from veadk.knowledgebase.backends.vikingdb_knowledge_backend import (
        VikingDBKnowledgeBackend,
    )

    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "bp-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "bp-sk")
    monkeypatch.setattr(
        VikingDBKnowledgeBackend,
        "collection_status",
        lambda self: {"existed": True},
    )

    tos_config = TOSConfig(
        endpoint="tos-ap-southeast-1.bytepluses.com",
        region="ap-southeast-1",
    )
    backend = VikingDBKnowledgeBackend(
        index="vikingkl_we4191n",
        tos_config=tos_config,
    )

    assert backend.region == "cn-hongkong"
    assert backend.tos_config.region == "ap-southeast-1"
    assert backend.tos_config.endpoint == "tos-ap-southeast-1.bytepluses.com"


def test_byteplus_viking_knowledgebase_keeps_explicit_tos_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.knowledgebase.backends.vikingdb_knowledge_backend import (
        VikingDBKnowledgeBackend,
    )

    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("DATABASE_TOS_REGION", "ap-southeast-1")
    monkeypatch.setenv("DATABASE_TOS_ENDPOINT", "tos-ap-southeast-1.bytepluses.com")
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "bp-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "bp-sk")
    monkeypatch.setattr(
        VikingDBKnowledgeBackend,
        "collection_status",
        lambda self: {"existed": True},
    )

    backend = VikingDBKnowledgeBackend(index="vikingkl_we4191n")

    assert backend.region == "cn-hongkong"
    assert backend.tos_config.region == "ap-southeast-1"
    assert backend.tos_config.endpoint == "tos-ap-southeast-1.bytepluses.com"


def test_volces_viking_knowledgebase_uses_region_env_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.knowledgebase.backends.vikingdb_knowledge_backend import (
        VikingDBKnowledgeBackend,
    )

    monkeypatch.setenv("CLOUD_PROVIDER", "volces")
    monkeypatch.delenv("DATABASE_VIKING_REGION", raising=False)
    monkeypatch.setenv("REGION", "cn-shanghai")
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "volc-ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "volc-sk")
    monkeypatch.setattr(
        VikingDBKnowledgeBackend,
        "collection_status",
        lambda self: {"existed": True},
    )

    backend = VikingDBKnowledgeBackend(index="vikingkl_we4191n")

    assert backend.region == "cn-shanghai"
    assert backend.host == "api-knowledgebase.mlp.cn-shanghai.volces.com"
    assert backend.base_url == "https://api-knowledgebase.mlp.cn-shanghai.volces.com"


def test_byteplus_viking_knowledgebase_get_tos_client_uses_aligned_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import veadk.knowledgebase.backends.vikingdb_knowledge_backend as module

    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "bp-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "bp-sk")
    monkeypatch.setattr(
        module.VikingDBKnowledgeBackend,
        "collection_status",
        lambda self: {"existed": True},
    )
    captured: dict[str, Any] = {}

    class _FakeVeTOS:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(module, "VeTOS", _FakeVeTOS)

    backend = module.VikingDBKnowledgeBackend(index="vikingkl_we4191n")
    backend._get_tos_client("kb-bucket")

    assert captured["region"] == "cn-hongkong"
    assert captured["bucket_name"] == "kb-bucket"


def test_byteplus_viking_knowledgebase_bucket_creation_uses_aligned_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import veadk.configs.database_configs as config_module
    from veadk.knowledgebase.backends.vikingdb_knowledge_backend import (
        VikingDBKnowledgeBackend,
    )

    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("DATABASE_TOS_BUCKET", "kb-bucket")
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "bp-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "bp-sk")
    monkeypatch.setattr(
        VikingDBKnowledgeBackend,
        "collection_status",
        lambda self: {"existed": True},
    )
    captured: dict[str, Any] = {}

    class _FakeVeTOS:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

        def create_bucket(self) -> bool:
            captured["create_bucket_called"] = True
            return True

    monkeypatch.setattr(config_module, "VeTOS", _FakeVeTOS)

    backend = VikingDBKnowledgeBackend(index="vikingkl_we4191n")

    assert backend.tos_config.bucket == "kb-bucket"
    assert captured["region"] == "cn-hongkong"
    assert captured["bucket_name"] == "kb-bucket"
    assert captured["create_bucket_called"] is True
