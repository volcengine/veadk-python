# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from types import SimpleNamespace

import pytest

from veadk.cli.studio_cloud_credentials import StudioCloudCredentials
from veadk.cli.studio_skill_storage import (
    StudioSkillStorageError,
    upload_skill_archive,
)


@pytest.mark.parametrize(
    ("provider", "region", "endpoint"),
    [
        ("volcengine", "cn-beijing", "tos-cn-beijing.volces.com"),
        (
            "byteplus",
            "ap-southeast-1",
            "tos-ap-southeast-1.bytepluses.com",
        ),
    ],
)
def test_upload_skill_archive_uses_the_provider_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    provider: str,
    region: str,
    endpoint: str,
) -> None:
    archive = tmp_path / "release-notes-deadbeef.zip"
    archive.write_bytes(b"skill")
    clients = []

    class TosClient:
        def __init__(
            self,
            access_key,
            secret_key,
            actual_endpoint,
            actual_region,
            **kwargs,
        ):
            self.options = (
                access_key,
                secret_key,
                actual_endpoint,
                actual_region,
                kwargs,
            )
            self.uploads = []
            self.closed = False
            clients.append(self)

        def list_buckets(self):
            return SimpleNamespace(
                buckets=[
                    SimpleNamespace(name="owned-bucket", location=region),
                ]
            )

        def put_object_from_file(self, **kwargs):
            self.uploads.append(kwargs)

        def close(self):
            self.closed = True

    monkeypatch.setattr("tos.TosClientV2", TosClient)
    if provider == "volcengine":
        monkeypatch.setattr(
            "agentkit.platform.VolcConfiguration.get_service_credentials",
            lambda self, service: SimpleNamespace(
                access_key="iam-ak",
                secret_key="iam-sk",
                session_token="iam-token",
            ),
        )
    monkeypatch.setattr(
        "veadk.cli.studio_skill_storage.resolve_studio_cloud_credentials",
        lambda actual_provider: StudioCloudCredentials(
            access_key="iam-ak",
            secret_key="iam-sk",
            session_token="iam-token",
            source="vefaas_iam",
        ),
    )

    result = upload_skill_archive(
        archive,
        configured_bucket="owned-bucket",
        prefix="agentkit/skills",
        region=region,
        provider=provider,
    )

    assert result.bucket_name == "owned-bucket"
    assert result.object_key == "agentkit/skills/release-notes-deadbeef.zip"
    assert result.url == (
        f"https://owned-bucket.{endpoint}/agentkit/skills/release-notes-deadbeef.zip"
    )
    assert clients[0].options == (
        "iam-ak",
        "iam-sk",
        endpoint,
        region,
        {
            "security_token": "iam-token",
            "connection_time": 10,
            "socket_timeout": 30,
            "max_retry_count": 2,
        },
    )
    assert clients[0].uploads == [
        {
            "bucket": "owned-bucket",
            "key": "agentkit/skills/release-notes-deadbeef.zip",
            "file_path": str(archive),
        }
    ]
    assert clients[0].closed is True


def test_upload_skill_archive_creates_and_verifies_a_missing_bucket(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    archive = tmp_path / "skill.zip"
    archive.write_bytes(b"skill")
    list_results = iter(
        [
            [],
            [
                SimpleNamespace(
                    name="new-bucket",
                    location="ap-southeast-1",
                )
            ],
        ]
    )
    create_calls = []

    class TosClient:
        def __init__(self, *args, **kwargs):
            pass

        def list_buckets(self):
            return SimpleNamespace(buckets=next(list_results))

        def create_bucket(self, **kwargs):
            create_calls.append(kwargs)

        def put_object_from_file(self, **kwargs):
            pass

    monkeypatch.setattr("tos.TosClientV2", TosClient)
    monkeypatch.setattr(
        "veadk.cli.studio_skill_storage.resolve_studio_cloud_credentials",
        lambda provider: StudioCloudCredentials(
            access_key="iam-ak",
            secret_key="iam-sk",
            session_token="",
            source="vefaas_iam",
        ),
    )

    result = upload_skill_archive(
        archive,
        configured_bucket="new-bucket",
        region="ap-southeast-1",
        provider="byteplus",
    )

    assert result.bucket_name == "new-bucket"
    assert create_calls == [{"bucket": "new-bucket"}]


def test_upload_skill_archive_rejects_an_owned_bucket_in_another_region(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    archive = tmp_path / "skill.zip"
    archive.write_bytes(b"skill")
    uploads = []

    class TosClient:
        def __init__(self, *args, **kwargs):
            pass

        def list_buckets(self):
            return SimpleNamespace(
                buckets=[
                    SimpleNamespace(
                        name="wrong-region",
                        location="cn-hongkong",
                    )
                ]
            )

        def put_object_from_file(self, **kwargs):
            uploads.append(kwargs)

    monkeypatch.setattr("tos.TosClientV2", TosClient)
    monkeypatch.setattr(
        "veadk.cli.studio_skill_storage.resolve_studio_cloud_credentials",
        lambda provider: StudioCloudCredentials(
            access_key="iam-ak",
            secret_key="iam-sk",
            session_token="iam-token",
            source="vefaas_iam",
        ),
    )

    with pytest.raises(StudioSkillStorageError, match="cn-hongkong"):
        upload_skill_archive(
            archive,
            configured_bucket="wrong-region",
            region="ap-southeast-1",
            provider="byteplus",
        )

    assert uploads == []


def test_upload_skill_archive_rejects_a_bucket_name_collision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    archive = tmp_path / "skill.zip"
    archive.write_bytes(b"skill")

    class BucketConflict(Exception):
        status_code = 409

    class TosClient:
        def __init__(self, *args, **kwargs):
            pass

        def list_buckets(self):
            return SimpleNamespace(buckets=[])

        def create_bucket(self, **kwargs):
            raise BucketConflict()

    monkeypatch.setattr("tos.TosClientV2", TosClient)
    monkeypatch.setattr(
        "veadk.cli.studio_skill_storage.resolve_studio_cloud_credentials",
        lambda provider: StudioCloudCredentials(
            access_key="iam-ak",
            secret_key="iam-sk",
            session_token="",
            source="vefaas_iam",
        ),
    )
    monkeypatch.setattr(
        "veadk.cli.studio_skill_storage._BUCKET_OWNERSHIP_ATTEMPTS",
        1,
    )

    with pytest.raises(StudioSkillStorageError, match="not owned"):
        upload_skill_archive(
            archive,
            configured_bucket="someone-elses-bucket",
            region="ap-southeast-1",
            provider="byteplus",
        )
