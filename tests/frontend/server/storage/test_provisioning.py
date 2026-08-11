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

from types import SimpleNamespace
from typing import Any

import pytest

from frontend.server.storage import provisioning


class _FakeTosClient:
    def __init__(
        self,
        buckets: list[tuple[str, str]] | None = None,
        create_error: Exception | None = None,
    ) -> None:
        self.buckets = list(buckets or [])
        self.create_error = create_error
        self.created: list[dict[str, Any]] = []

    def list_buckets(self) -> SimpleNamespace:
        return SimpleNamespace(
            buckets=[
                SimpleNamespace(name=name, location=region)
                for name, region in self.buckets
            ]
        )

    def create_bucket(self, **kwargs: Any) -> None:
        self.created.append(kwargs)
        if self.create_error is not None:
            raise self.create_error
        self.buckets.append((str(kwargs["bucket"]), "cn-beijing"))


def _patch_cloud(
    monkeypatch: pytest.MonkeyPatch,
    client: _FakeTosClient,
    *,
    account_id: str = "2100123456",
) -> None:
    monkeypatch.setattr(
        provisioning,
        "_resolve_account_id",
        lambda **_kwargs: account_id,
    )
    monkeypatch.setattr(
        provisioning,
        "_create_tos_client",
        lambda **_kwargs: client,
    )


def test_auto_storage_uses_stable_account_bucket_and_creates_it_private(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeTosClient()
    _patch_cloud(monkeypatch, client)

    config = provisioning.resolve_studio_storage_for_deploy(
        provider="volcengine",
        region="cn-beijing",
        access_key="ak",
        secret_key="sk",
        source={},
    )

    assert config.bucket == "veadk-studio-2100123456"
    assert config.region == "cn-beijing"
    assert config.object_host == ("veadk-studio-2100123456.tos-cn-beijing.volces.com")
    assert client.created == [{"bucket": "veadk-studio-2100123456"}]


def test_auto_storage_reuses_the_same_bucket_on_repeated_deploy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeTosClient(
        [("veadk-studio-2100123456", "cn-beijing")],
    )
    _patch_cloud(monkeypatch, client)

    config = provisioning.resolve_studio_storage_for_deploy(
        provider="volcengine",
        region="cn-beijing",
        access_key="ak",
        secret_key="sk",
        source={},
    )

    assert config.bucket == "veadk-studio-2100123456"
    assert client.created == []


def test_auto_storage_rejects_reusing_account_bucket_in_another_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeTosClient(
        [("veadk-studio-2100123456", "cn-beijing")],
    )
    _patch_cloud(monkeypatch, client)

    with pytest.raises(
        provisioning.StudioStorageProvisioningError,
        match="cn-beijing.*cn-shanghai",
    ):
        provisioning.resolve_studio_storage_for_deploy(
            provider="volcengine",
            region="cn-shanghai",
            access_key="ak",
            secret_key="sk",
            source={},
        )

    assert client.created == []


def test_auto_storage_reports_global_name_collision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BucketAlreadyExistsError(RuntimeError):
        status_code = 409

    error = BucketAlreadyExistsError("BucketAlreadyExists")
    client = _FakeTosClient(create_error=error)
    _patch_cloud(monkeypatch, client)

    with pytest.raises(
        provisioning.StudioStorageProvisioningError,
        match="已被其他账号占用",
    ):
        provisioning.resolve_studio_storage_for_deploy(
            provider="volcengine",
            region="cn-beijing",
            access_key="ak",
            secret_key="sk",
            source={},
        )


def test_explicit_bucket_is_reused_without_resolving_account_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeTosClient([("admin-storage", "ap-southeast-1")])
    monkeypatch.setattr(
        provisioning,
        "_resolve_account_id",
        lambda **_kwargs: pytest.fail("explicit bucket must not resolve account ID"),
    )
    monkeypatch.setattr(
        provisioning,
        "_create_tos_client",
        lambda **_kwargs: client,
    )

    config = provisioning.resolve_studio_storage_for_deploy(
        provider="byteplus",
        region="ap-southeast-1",
        access_key="ak",
        secret_key="sk",
        source={"VEADK_STUDIO_TOS_BUCKET": "admin-storage"},
    )

    assert config.bucket == "admin-storage"
    assert config.object_host == "admin-storage.tos-ap-southeast-1.bytepluses.com"
    assert client.created == []


def test_explicit_bucket_must_already_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeTosClient()
    _patch_cloud(monkeypatch, client)

    with pytest.raises(
        provisioning.StudioStorageProvisioningError,
        match="管理员配置的 TOS 桶 admin-storage 不存在",
    ):
        provisioning.resolve_studio_storage_for_deploy(
            provider="volcengine",
            region="cn-beijing",
            access_key="ak",
            secret_key="sk",
            source={"VEADK_STUDIO_TOS_BUCKET": "admin-storage"},
        )

    assert client.created == []
