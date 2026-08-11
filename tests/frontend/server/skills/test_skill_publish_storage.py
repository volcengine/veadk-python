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

from types import SimpleNamespace

import pytest

from frontend.server.skills import storage


class _FakeTosClient:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.created: list[str] = []
        self.uploads: list[dict[str, object]] = []

    def list_buckets(self) -> SimpleNamespace:
        return SimpleNamespace(
            buckets=[
                SimpleNamespace(
                    name="veadk-studio-3001037806",
                    location="ap-southeast-1",
                )
            ]
        )

    def create_bucket(self, *, bucket: str) -> None:
        self.created.append(bucket)

    def put_object_from_file(self, **kwargs: object) -> None:
        self.uploads.append(kwargs)


def test_studio_bucket_wins_without_generating_account_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("VEADK_STUDIO_TOS_BUCKET", "veadk-studio-3001037806")
    monkeypatch.setenv("VEADK_STUDIO_TOS_REGION", "ap-southeast-1")

    from agentkit.toolkit.volcengine.services.tos_service import TOSService

    monkeypatch.setattr(
        TOSService,
        "generate_bucket_name",
        lambda: pytest.fail("Studio bucket must avoid generate_bucket_name()"),
    )

    result = storage.resolve_skill_publish_storage(
        region="ap-southeast-1",
        config_bucket="agentkit-config-bucket",
        config_prefix="configured-prefix",
    )

    assert result.bucket == "veadk-studio-3001037806"
    assert result.prefix == "configured-prefix"
    assert result.bucket_mode == "studio-storage"
    assert result.endpoint == "tos-ap-southeast-1.bytepluses.com"


def test_skill_bucket_env_still_overrides_studio_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("VEADK_SKILL_CREATOR_TOS_BUCKET", "skill-upload-bucket")
    monkeypatch.setenv("VEADK_STUDIO_TOS_BUCKET", "veadk-studio-3001037806")
    monkeypatch.setenv("VEADK_STUDIO_TOS_REGION", "ap-southeast-1")

    result = storage.resolve_skill_publish_storage(region="ap-southeast-1")

    assert result.bucket == "skill-upload-bucket"
    assert result.bucket_mode == "skill-env"


def test_studio_bucket_region_mismatch_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("VEADK_STUDIO_TOS_BUCKET", "veadk-studio-3001037806")
    monkeypatch.setenv("VEADK_STUDIO_TOS_REGION", "ap-southeast-1")

    with pytest.raises(storage.SkillPublishStorageError, match="地域不一致"):
        storage.resolve_skill_publish_storage(region="cn-beijing")


def test_auto_generated_bucket_is_last_resort(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "volcengine")
    monkeypatch.delenv("VEADK_SKILL_CREATOR_TOS_BUCKET", raising=False)
    monkeypatch.delenv("VEADK_STUDIO_TOS_BUCKET", raising=False)
    monkeypatch.delenv("VEADK_STUDIO_TOS_REGION", raising=False)

    from agentkit.toolkit.volcengine.services.tos_service import TOSService

    monkeypatch.setattr(
        TOSService, "generate_bucket_name", lambda: "agentkit-platform-1"
    )

    result = storage.resolve_skill_publish_storage(region="cn-beijing")

    assert result.bucket == "agentkit-platform-1"
    assert result.bucket_mode == "auto-generated"
    assert result.endpoint == "tos-cn-beijing.volces.com"


def test_byteplus_upload_uses_explicit_tos_client_with_session_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "sk")
    monkeypatch.setenv("BYTEPLUS_SESSION_TOKEN", "token")
    fake_client = _FakeTosClient()

    import tos

    def make_client(**kwargs: object) -> _FakeTosClient:
        fake_client.kwargs = kwargs
        return fake_client

    monkeypatch.setattr(tos, "TosClientV2", make_client)
    publish_storage = storage.resolve_skill_publish_storage(
        region="ap-southeast-1",
        source={
            "VEADK_STUDIO_TOS_BUCKET": "veadk-studio-3001037806",
            "VEADK_STUDIO_TOS_REGION": "ap-southeast-1",
        },
    )
    credentials = storage.resolve_skill_publish_credentials(provider="byteplus")
    archive_path = tmp_path / "demo.zip"
    archive_path.write_bytes(b"zip")

    storage.ensure_skill_publish_bucket(publish_storage, credentials)
    tos_url = storage.upload_skill_archive(
        str(archive_path),
        publish_storage,
        credentials,
    )

    assert fake_client.kwargs == {
        "ak": "ak",
        "sk": "sk",
        "security_token": "token",
        "endpoint": "tos-ap-southeast-1.bytepluses.com",
        "region": "ap-southeast-1",
    }
    assert fake_client.created == []
    assert fake_client.uploads[0]["bucket"] == "veadk-studio-3001037806"
    assert fake_client.uploads[0]["key"] == "agentkit/skills/demo.zip"
    assert tos_url == (
        "https://veadk-studio-3001037806.tos-ap-southeast-1.bytepluses.com/"
        "agentkit/skills/demo.zip"
    )


def test_byteplus_credentials_can_read_iam_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.delenv("BYTEPLUS_ACCESS_KEY", raising=False)
    monkeypatch.delenv("BYTEPLUS_SECRET_KEY", raising=False)
    iam_file = tmp_path / "credential"
    iam_file.write_text(
        '{"access_key_id":"iam-ak","secret_access_key":"iam-sk",'
        '"session_token":"iam-token"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(storage, "_IAM_CREDENTIAL_PATH", iam_file)

    credentials = storage.resolve_skill_publish_credentials(provider="byteplus")

    assert credentials.access_key == "iam-ak"
    assert credentials.secret_key == "iam-sk"
    assert credentials.session_token == "iam-token"
    assert credentials.source == "iam-file"
