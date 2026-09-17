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

import importlib
import sys
import types
from typing import Any

import pytest


def _load_backend_module(monkeypatch: pytest.MonkeyPatch):
    class FakeAPIKey:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    class FakeIAM:
        def __init__(self, **_: Any) -> None:
            pass

    class FakeVikingDBModule(types.ModuleType):
        APIKey: type[FakeAPIKey]
        IAM: type[FakeIAM]

    class FakeVikingMem:
        def __init__(self, **_: Any) -> None:
            pass

    class FakeVikingDBMemoryModule(types.ModuleType):
        VikingMem: type[FakeVikingMem]

    vikingdb_module = FakeVikingDBModule("vikingdb")
    vikingdb_module.APIKey = FakeAPIKey
    vikingdb_module.IAM = FakeIAM
    vikingdb_memory_module = FakeVikingDBMemoryModule("vikingdb.memory")
    vikingdb_memory_module.VikingMem = FakeVikingMem
    monkeypatch.setitem(sys.modules, "vikingdb", vikingdb_module)
    monkeypatch.setitem(sys.modules, "vikingdb.memory", vikingdb_memory_module)

    module_name = "veadk.memory.long_term_memory_backends.vikingdb_memory_backend"
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def test_byteplus_viking_memory_uses_fixed_hong_kong_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_backend_module(monkeypatch)
    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("DATABASE_VIKING_REGION", "cn-beijing")
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "bp-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "bp-sk")
    monkeypatch.setattr(
        module.VikingDBLTMBackend,
        "_collection_exist",
        lambda self: True,
    )

    backend = module.VikingDBLTMBackend(index="agent_memory")

    assert backend.region == "cn-hongkong"


def test_viking_memory_agentkit_provider_selects_byteplus_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_backend_module(monkeypatch)
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.delenv("CLOUD_PROVIDER", raising=False)
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "bp-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "bp-sk")
    monkeypatch.setattr(
        module.VikingDBLTMBackend,
        "_collection_exist",
        lambda self: True,
    )

    backend = module.VikingDBLTMBackend(index="agent_memory")

    assert backend.cloud_provider == "byteplus"
    assert backend.region == "cn-hongkong"


def test_viking_memory_reads_api_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_backend_module(monkeypatch)
    monkeypatch.setenv("DATABASE_VIKINGMEM_API_KEY", "mem-api-key")
    monkeypatch.setattr(
        module.VikingDBLTMBackend,
        "_collection_exist",
        lambda self: True,
    )

    backend = module.VikingDBLTMBackend(index="agent_memory")

    assert backend.api_key == "mem-api-key"


def test_viking_memory_sdk_client_uses_api_key_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_backend_module(monkeypatch)
    captured: dict[str, Any] = {}

    class UnexpectedClient:
        def __init__(self, **kwargs: Any) -> None:
            raise AssertionError("API key SDK client must not use management client")

    class FakeAPIKey:
        def __init__(self, **kwargs: Any) -> None:
            captured["api_key_kwargs"] = kwargs

    class FakeVikingMem:
        def __init__(self, **kwargs: Any) -> None:
            captured["viking_mem_kwargs"] = kwargs

    monkeypatch.setattr(
        module.VikingDBLTMBackend,
        "_collection_exist",
        lambda self: True,
    )
    monkeypatch.setattr(
        module.VikingDBLTMBackend,
        "_get_ak_sk_sts",
        lambda self: (_ for _ in ()).throw(AssertionError("AK/SK not expected")),
    )
    monkeypatch.setattr(module, "VikingDBMemoryClient", UnexpectedClient)
    monkeypatch.setattr(module, "APIKey", FakeAPIKey)
    monkeypatch.setattr(module, "VikingMem", FakeVikingMem)
    monkeypatch.setenv("DATABASE_VIKINGMEM_BASE_URL", "http://memory.example")

    backend = module.VikingDBLTMBackend(
        index="agent_memory",
        api_key="mem-api-key",
        volcengine_access_key=None,
        volcengine_secret_key=None,
    )
    backend._get_sdk_client()

    assert captured["api_key_kwargs"] == {"api_key": "mem-api-key"}
    assert isinstance(captured["viking_mem_kwargs"]["auth"], FakeAPIKey)
    assert captured["viking_mem_kwargs"]["host"] == "memory.example"
    assert captured["viking_mem_kwargs"]["scheme"] == "http"


def test_viking_memory_api_key_only_skips_collection_management_precheck(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_backend_module(monkeypatch)
    monkeypatch.setenv("DATABASE_VIKINGMEM_API_KEY", "mem-api-key")
    monkeypatch.setattr(
        module.VikingDBLTMBackend,
        "_collection_exist",
        lambda self: (_ for _ in ()).throw(
            AssertionError("API-key-only init must not check collection management")
        ),
    )

    backend = module.VikingDBLTMBackend(
        index="agent_memory",
        volcengine_access_key=None,
        volcengine_secret_key=None,
    )

    assert backend.api_key == "mem-api-key"


def test_viking_memory_get_user_profile_uses_sdk_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_backend_module(monkeypatch)
    captured: dict[str, Any] = {}

    class FakeCollection:
        def search_memory(self, **kwargs: Any) -> dict[str, Any]:
            captured["search_kwargs"] = kwargs
            return {
                "code": 0,
                "data": {
                    "result_list": [
                        {"memory_info": {"user_profile": "likes concise answers"}}
                    ]
                },
            }

    class FakeSdkClient:
        def get_collection(self, **kwargs: Any) -> FakeCollection:
            captured["get_collection_kwargs"] = kwargs
            return FakeCollection()

    monkeypatch.setattr(
        module.VikingDBLTMBackend,
        "_collection_exist",
        lambda self: True,
    )
    monkeypatch.setattr(
        module.VikingDBLTMBackend,
        "_get_sdk_client",
        lambda self: FakeSdkClient(),
    )

    backend = module.VikingDBLTMBackend(index="agent_memory", api_key="mem-api-key")

    assert backend.get_user_profile("user-42") == "likes concise answers"
    assert captured["get_collection_kwargs"] == {
        "collection_name": "agent_memory",
        "project_name": "default",
    }
    assert captured["search_kwargs"] == {
        "filter": {"user_id": ["user-42"], "memory_category": 1},
        "limit": 5000,
    }


def test_viking_memory_get_user_profile_raises_on_error_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_backend_module(monkeypatch)

    class FakeCollection:
        def search_memory(self, **kwargs: Any) -> dict[str, Any]:
            return {"code": 1000001, "message": "unauthorized"}

    class FakeSdkClient:
        def get_collection(self, **kwargs: Any) -> FakeCollection:
            return FakeCollection()

    monkeypatch.setattr(
        module.VikingDBLTMBackend,
        "_collection_exist",
        lambda self: True,
    )
    monkeypatch.setattr(
        module.VikingDBLTMBackend,
        "_get_sdk_client",
        lambda self: FakeSdkClient(),
    )

    backend = module.VikingDBLTMBackend(index="agent_memory", api_key="mem-api-key")

    with pytest.raises(ValueError, match="Get VikingDB user profile error"):
        backend.get_user_profile("user-42")


def test_viking_memory_get_user_profile_returns_empty_when_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_backend_module(monkeypatch)

    class FakeCollection:
        def search_memory(self, **kwargs: Any) -> dict[str, Any]:
            return {"code": 0, "data": {"result_list": []}}

    class FakeSdkClient:
        def get_collection(self, **kwargs: Any) -> FakeCollection:
            return FakeCollection()

    monkeypatch.setattr(
        module.VikingDBLTMBackend,
        "_collection_exist",
        lambda self: True,
    )
    monkeypatch.setattr(
        module.VikingDBLTMBackend,
        "_get_sdk_client",
        lambda self: FakeSdkClient(),
    )

    backend = module.VikingDBLTMBackend(index="agent_memory", api_key="mem-api-key")

    assert backend.get_user_profile("user-42") == ""


def test_byteplus_viking_memory_ignores_explicit_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_backend_module(monkeypatch)
    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "bp-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "bp-sk")
    monkeypatch.setattr(
        module.VikingDBLTMBackend,
        "_collection_exist",
        lambda self: True,
    )

    backend = module.VikingDBLTMBackend(index="agent_memory", region="ap-southeast-1")

    assert backend.region == "cn-hongkong"


def test_byteplus_viking_memory_client_uses_fixed_hong_kong_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_backend_module(monkeypatch)
    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "bp-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "bp-sk")
    monkeypatch.setattr(
        module.VikingDBLTMBackend,
        "_collection_exist",
        lambda self: True,
    )

    captured: dict[str, str] = {}

    class FakeClient:
        def __init__(self, **kwargs: str) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(module, "VikingDBMemoryClient", FakeClient)

    backend = module.VikingDBLTMBackend(index="agent_memory")
    backend._get_client()

    assert backend.region == "cn-hongkong"
    assert captured["region"] == "cn-hongkong"
    assert captured["host"] == "api-knowledgebase.mlp.cn-hongkong.bytepluses.com"


def test_direct_byteplus_viking_memory_client_uses_fixed_hong_kong_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.integrations.ve_viking_db_memory.ve_viking_db_memory import (
        VikingDBMemoryClient,
    )

    if hasattr(VikingDBMemoryClient, "_instance"):
        delattr(VikingDBMemoryClient, "_instance")
    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.setattr(
        VikingDBMemoryClient,
        "get_body",
        lambda self, api, params, body: "{}",
    )

    client = VikingDBMemoryClient(region="ap-southeast-1")

    assert client.get_host() == "api-knowledgebase.mlp.cn-hongkong.bytepluses.com"
    assert client.service_info.credentials.region == "cn-hongkong"


def test_direct_viking_memory_client_lists_collections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.integrations.ve_viking_db_memory.ve_viking_db_memory import (
        VikingDBMemoryClient,
    )

    if hasattr(VikingDBMemoryClient, "_instance"):
        delattr(VikingDBMemoryClient, "_instance")
    monkeypatch.setattr(
        VikingDBMemoryClient,
        "get_body",
        lambda self, api, params, body: "{}",
    )
    captured: dict[str, Any] = {}

    def fake_json(self, api: str, params: dict[str, Any], body: str) -> str:
        captured.update({"api": api, "params": params, "body": body})
        return '{"Result":{"Collections":[{"CollectionName":"agent_memory"}]}}'

    monkeypatch.setattr(VikingDBMemoryClient, "json", fake_json)

    client = VikingDBMemoryClient(region="cn-beijing")
    result = client.list_collections(
        project="agent-project",
        page_number=2,
        page_size=50,
    )

    assert captured["api"] == "ListCollection"
    assert captured["body"] == (
        '{"ProjectName": "agent-project", "PageNumber": 2, "PageSize": 50}'
    )
    assert result["Result"]["Collections"][0]["CollectionName"] == "agent_memory"


def test_direct_viking_memory_client_rejects_api_key_for_management(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.integrations.ve_viking_db_memory.ve_viking_db_memory import (
        VikingDBMemoryClient,
    )

    if hasattr(VikingDBMemoryClient, "_instance"):
        delattr(VikingDBMemoryClient, "_instance")

    with pytest.raises(ValueError, match="collection management requires AK/SK"):
        VikingDBMemoryClient(region="cn-beijing", api_key="mem-api-key")


def test_viking_memory_ignores_empty_yaml_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_backend_module(monkeypatch)
    monkeypatch.setenv("DATABASE_VIKINGMEM_API_KEY", "None")
    monkeypatch.setattr(
        module.VikingDBLTMBackend,
        "_collection_exist",
        lambda self: True,
    )

    backend = module.VikingDBLTMBackend(index="agent_memory")

    assert backend.api_key is None


def test_viking_memory_empty_api_key_parameter_falls_back_to_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_backend_module(monkeypatch)
    monkeypatch.setenv("DATABASE_VIKINGMEM_API_KEY", "mem-api-key")
    monkeypatch.setattr(
        module.VikingDBLTMBackend,
        "_collection_exist",
        lambda self: True,
    )

    backend = module.VikingDBLTMBackend(index="agent_memory", api_key="")

    assert backend.api_key == "mem-api-key"


def test_byteplus_viking_memory_keeps_hong_kong_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_backend_module(monkeypatch)
    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("DATABASE_VIKING_REGION", "cn-hongkong")
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "bp-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "bp-sk")
    monkeypatch.setattr(
        module.VikingDBLTMBackend,
        "_collection_exist",
        lambda self: True,
    )

    backend = module.VikingDBLTMBackend(index="agent_memory")

    assert backend.region == "cn-hongkong"


def test_volcengine_viking_memory_keeps_volcengine_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_backend_module(monkeypatch)
    monkeypatch.setenv("CLOUD_PROVIDER", "volcengine")
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "volcengine")
    monkeypatch.setenv("DATABASE_VIKING_REGION", "cn-shanghai")
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "volc-ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "volc-sk")
    monkeypatch.setattr(
        module.VikingDBLTMBackend,
        "_collection_exist",
        lambda self: True,
    )

    backend = module.VikingDBLTMBackend(index="agent_memory")

    assert backend.region == "cn-shanghai"


def test_volcengine_viking_memory_uses_region_env_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_backend_module(monkeypatch)
    monkeypatch.setenv("CLOUD_PROVIDER", "volcengine")
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "volcengine")
    monkeypatch.delenv("DATABASE_VIKING_REGION", raising=False)
    monkeypatch.setenv("REGION", "cn-shanghai")
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "volc-ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "volc-sk")
    monkeypatch.setattr(
        module.VikingDBLTMBackend,
        "_collection_exist",
        lambda self: True,
    )

    backend = module.VikingDBLTMBackend(index="agent_memory")

    assert backend.region == "cn-shanghai"


def test_volcengine_viking_memory_database_region_wins_over_region_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_backend_module(monkeypatch)
    monkeypatch.setenv("CLOUD_PROVIDER", "volcengine")
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "volcengine")
    monkeypatch.setenv("DATABASE_VIKING_REGION", "cn-beijing")
    monkeypatch.setenv("REGION", "cn-shanghai")
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "volc-ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "volc-sk")
    monkeypatch.setattr(
        module.VikingDBLTMBackend,
        "_collection_exist",
        lambda self: True,
    )

    backend = module.VikingDBLTMBackend(index="agent_memory")

    assert backend.region == "cn-beijing"


def test_direct_volcengine_viking_memory_client_uses_region_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.integrations.ve_viking_db_memory.ve_viking_db_memory import (
        VikingDBMemoryClient,
    )

    if hasattr(VikingDBMemoryClient, "_instance"):
        delattr(VikingDBMemoryClient, "_instance")
    monkeypatch.setenv("CLOUD_PROVIDER", "volcengine")
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "volcengine")
    monkeypatch.setenv("REGION", "cn-shanghai")
    monkeypatch.setattr(
        VikingDBMemoryClient,
        "get_body",
        lambda self, api, params, body: "{}",
    )

    client = VikingDBMemoryClient()

    assert client.get_host() == "api-knowledgebase.mlp.cn-shanghai.volces.com"
    assert client.service_info.credentials.region == "cn-shanghai"
