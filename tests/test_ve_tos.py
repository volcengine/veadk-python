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

import sys
from types import SimpleNamespace

import pytest
from google.genai import types

from veadk.integrations.ve_tos.ve_tos import VeTOS
from veadk.runner import _upload_image_to_tos


class _FakeTosClient:
    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.put_calls = []

    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)


@pytest.fixture
def fake_tos(monkeypatch):
    module = SimpleNamespace(TosClientV2=_FakeTosClient)
    monkeypatch.setitem(sys.modules, "tos", module)
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "test-ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "test-sk")
    return module


def test_ve_tos_uses_bucket_and_session_token_from_environment(monkeypatch, fake_tos):
    monkeypatch.setenv("DATABASE_TOS_BUCKET", "customer-bucket")
    monkeypatch.setenv("VOLCENGINE_SESSION_TOKEN", "test-token")

    client = VeTOS()

    assert client.bucket_name == "customer-bucket"
    assert client.session_token == "test-token"
    assert client._client.init_kwargs["security_token"] == "test-token"


def test_ve_tos_explicit_bucket_wins_over_environment(monkeypatch, fake_tos):
    monkeypatch.setenv("DATABASE_TOS_BUCKET", "environment-bucket")

    client = VeTOS(bucket_name="explicit-bucket")

    assert client.bucket_name == "explicit-bucket"


def test_ve_tos_uses_region_env_as_fallback(monkeypatch, fake_tos):
    monkeypatch.setenv("CLOUD_PROVIDER", "volces")
    monkeypatch.delenv("DATABASE_TOS_REGION", raising=False)
    monkeypatch.setenv("REGION", "cn-shanghai")

    client = VeTOS()

    assert client.region == "cn-shanghai"
    assert client._client.init_kwargs["region"] == "cn-shanghai"
    assert client._client.init_kwargs["endpoint"] == "tos-cn-shanghai.volces.com"


def test_ve_tos_database_region_wins_over_region_env(monkeypatch, fake_tos):
    monkeypatch.setenv("CLOUD_PROVIDER", "volces")
    monkeypatch.setenv("DATABASE_TOS_REGION", "cn-beijing")
    monkeypatch.setenv("REGION", "cn-shanghai")

    client = VeTOS()

    assert client.region == "cn-beijing"
    assert client._client.init_kwargs["region"] == "cn-beijing"
    assert client._client.init_kwargs["endpoint"] == "tos-cn-beijing.volces.com"


def test_tos_config_uses_region_env_fallback_and_updates_endpoint(monkeypatch):
    from veadk.configs.database_configs import TOSConfig

    monkeypatch.delenv("AGENTKIT_CLOUD_PROVIDER", raising=False)
    monkeypatch.setenv("CLOUD_PROVIDER", "volces")
    monkeypatch.delenv("DATABASE_TOS_REGION", raising=False)
    monkeypatch.delenv("DATABASE_TOS_ENDPOINT", raising=False)
    monkeypatch.setenv("REGION", "cn-shanghai")

    config = TOSConfig()

    assert config.region == "cn-shanghai"
    assert config.endpoint == "tos-cn-shanghai.volces.com"


def test_tos_config_database_region_wins_over_region_env(monkeypatch):
    from veadk.configs.database_configs import TOSConfig

    monkeypatch.setenv("CLOUD_PROVIDER", "volces")
    monkeypatch.setenv("DATABASE_TOS_REGION", "cn-beijing")
    monkeypatch.delenv("DATABASE_TOS_ENDPOINT", raising=False)
    monkeypatch.setenv("REGION", "cn-shanghai")

    config = TOSConfig()

    assert config.region == "cn-beijing"
    assert config.endpoint == "tos-cn-beijing.volces.com"


def test_related_database_configs_use_region_env_fallback(monkeypatch):
    from veadk.configs.database_configs import (
        NormalTOSConfig,
        TOSContextBucketConfig,
        TOSVectorConfig,
        VikingKnowledgebaseConfig,
    )

    monkeypatch.delenv("AGENTKIT_CLOUD_PROVIDER", raising=False)
    monkeypatch.setenv("CLOUD_PROVIDER", "volces")
    for env_name in [
        "DATABASE_VIKING_REGION",
        "DATABASE_TOS_REGION",
        "DATABASE_TOS_ENDPOINT",
        "DATABASE_TOS_VECTOR_REGION",
        "DATABASE_TOS_VECTOR_ENDPOINT",
        "DATABASE_TOS_CONTEXT_REGION",
        "DATABASE_TOS_CONTEXT_ENDPOINT",
    ]:
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setenv("REGION", "cn-shanghai")

    viking_config = VikingKnowledgebaseConfig()
    normal_tos_config = NormalTOSConfig(bucket="bucket")
    vector_config = TOSVectorConfig()
    context_config = TOSContextBucketConfig()

    assert viking_config.region == "cn-shanghai"
    assert normal_tos_config.region == "cn-shanghai"
    assert normal_tos_config.endpoint == "tos-cn-shanghai.volces.com"
    assert vector_config.region == "cn-shanghai"
    assert vector_config.endpoint == "tosvectors-cn-shanghai.volces.com"
    assert context_config.region == "cn-shanghai"
    assert context_config.endpoint == "tos-cn-shanghai.volces.com"


def test_byteplus_related_database_configs_ignore_region_env(monkeypatch):
    from veadk.configs.database_configs import (
        NormalTOSConfig,
        TOSContextBucketConfig,
        TOSVectorConfig,
        VikingKnowledgebaseConfig,
    )

    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    for env_name in [
        "DATABASE_VIKING_REGION",
        "DATABASE_TOS_REGION",
        "DATABASE_TOS_ENDPOINT",
        "DATABASE_TOS_VECTOR_REGION",
        "DATABASE_TOS_VECTOR_ENDPOINT",
        "DATABASE_TOS_CONTEXT_REGION",
        "DATABASE_TOS_CONTEXT_ENDPOINT",
    ]:
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setenv("REGION", "cn-hongkong")

    assert VikingKnowledgebaseConfig().region == "cn-beijing"
    normal_tos_config = NormalTOSConfig(bucket="bucket")
    assert normal_tos_config.region == "cn-beijing"
    assert normal_tos_config.endpoint == "tos-cn-beijing.volces.com"
    assert TOSVectorConfig().region == "cn-beijing"
    assert TOSContextBucketConfig().region == "cn-beijing"


def test_byteplus_tos_config_ignores_region_env_fallback(monkeypatch):
    from veadk.configs.database_configs import TOSConfig

    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.delenv("DATABASE_TOS_REGION", raising=False)
    monkeypatch.delenv("DATABASE_TOS_ENDPOINT", raising=False)
    monkeypatch.setenv("REGION", "cn-hongkong")

    config = TOSConfig()

    assert config.region == "ap-southeast-1"
    assert config.endpoint == "tos-ap-southeast-1.bytepluses.com"


def test_byteplus_ve_tos_keeps_existing_region_precedence(monkeypatch, fake_tos):
    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("DATABASE_TOS_REGION", "ap-southeast-1")
    monkeypatch.setenv("REGION", "cn-hongkong")

    client = VeTOS()

    assert client.region == "cn-hongkong"
    assert client._client.init_kwargs["region"] == "cn-hongkong"
    assert client._client.init_kwargs["endpoint"] == "tos-cn-hongkong.bytepluses.com"


def test_byteplus_tos_config_database_region_still_sets_endpoint(monkeypatch):
    from veadk.configs.database_configs import TOSConfig

    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("DATABASE_TOS_REGION", "ap-southeast-1")
    monkeypatch.delenv("DATABASE_TOS_ENDPOINT", raising=False)
    monkeypatch.setenv("REGION", "cn-hongkong")

    config = TOSConfig()

    assert config.region == "ap-southeast-1"
    assert config.endpoint == "tos-ap-southeast-1.bytepluses.com"


@pytest.mark.asyncio
async def test_async_upload_bytes_reports_success(monkeypatch, fake_tos):
    client = VeTOS(bucket_name="test-bucket")
    monkeypatch.setattr(client, "_ensure_client_and_bucket", lambda bucket: True)

    uploaded = await client.async_upload_bytes(
        data=b"image-bytes", object_key="app/session/image.png"
    )

    assert uploaded is True
    assert client._client.put_calls == [
        {
            "bucket": "test-bucket",
            "key": "app/session/image.png",
            "content": b"image-bytes",
            "meta": None,
        }
    ]


@pytest.mark.asyncio
async def test_async_upload_bytes_reports_bucket_failure(monkeypatch, fake_tos):
    client = VeTOS(bucket_name="test-bucket")
    monkeypatch.setattr(client, "_ensure_client_and_bucket", lambda bucket: False)

    uploaded = await client.async_upload_bytes(data=b"image-bytes")

    assert uploaded is False


def _inline_image_part():
    return types.Part(
        inline_data=types.Blob(
            data=b"image-bytes",
            display_name="image.png",
            mime_type="image/png",
        )
    )


@pytest.mark.asyncio
async def test_inline_image_upload_failure_is_fail_open(monkeypatch, fake_tos):
    async def report_failure(self, **kwargs):
        return False

    monkeypatch.setattr(VeTOS, "async_upload_bytes", report_failure)
    part = _inline_image_part()

    await _upload_image_to_tos(part, "test-app", "test-user", "test-session")

    assert part.inline_data.display_name == "image.png"
    assert part.inline_data.data == b"image-bytes"


@pytest.mark.asyncio
async def test_inline_image_upload_exception_is_fail_open(monkeypatch, fake_tos):
    async def raise_upload_error(self, **kwargs):
        raise RuntimeError("simulated TOS outage")

    monkeypatch.setattr(VeTOS, "async_upload_bytes", raise_upload_error)
    part = _inline_image_part()

    await _upload_image_to_tos(part, "test-app", "test-user", "test-session")

    assert part.inline_data.display_name == "image.png"
    assert part.inline_data.data == b"image-bytes"
