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
    class FakeIAM:
        def __init__(self, **_: Any) -> None:
            pass

    class FakeVikingDBModule(types.ModuleType):
        IAM: type[FakeIAM]

    class FakeVikingMem:
        def __init__(self, **_: Any) -> None:
            pass

    class FakeVikingDBMemoryModule(types.ModuleType):
        VikingMem: type[FakeVikingMem]

    vikingdb_module = FakeVikingDBModule("vikingdb")
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
