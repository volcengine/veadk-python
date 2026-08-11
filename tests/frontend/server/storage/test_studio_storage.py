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

from frontend.server.storage import (
    STUDIO_STORAGE_ROOT_PREFIX,
    STUDIO_STORAGE_UNAVAILABLE_REASON,
    StudioStorageConfig,
    studio_object_key,
)
from veadk.multimodal.models import MediaRef


def test_studio_storage_derives_volcengine_endpoint_from_bucket_and_region(
    monkeypatch,
) -> None:
    monkeypatch.setenv("VEADK_STUDIO_TOS_BUCKET", "teststudio")
    monkeypatch.setenv("VEADK_STUDIO_TOS_REGION", "cn-beijing")

    config = StudioStorageConfig.from_env("volcengine")

    assert config.configured is True
    assert config.bucket == "teststudio"
    assert config.region == "cn-beijing"
    assert config.endpoint == "tos-cn-beijing.volces.com"
    assert config.object_host == "teststudio.tos-cn-beijing.volces.com"
    assert config.unavailable_reason == ""


def test_studio_storage_derives_byteplus_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("VEADK_STUDIO_TOS_BUCKET", "studio-assets")
    monkeypatch.setenv("VEADK_STUDIO_TOS_REGION", "ap-southeast-1")

    config = StudioStorageConfig.from_env("byteplus")

    assert config.endpoint == "tos-ap-southeast-1.bytepluses.com"
    assert config.object_host == ("studio-assets.tos-ap-southeast-1.bytepluses.com")


def test_incomplete_studio_storage_config_is_disabled(monkeypatch) -> None:
    monkeypatch.setenv("VEADK_STUDIO_TOS_BUCKET", "teststudio")
    monkeypatch.delenv("VEADK_STUDIO_TOS_REGION", raising=False)
    monkeypatch.delenv("VEADK_VIDEO_ASSET_STORAGE", raising=False)
    monkeypatch.delenv("VEADK_MEDIA_STORAGE", raising=False)

    config = StudioStorageConfig.from_env("volcengine")

    assert config.configured is False
    assert config.unavailable_reason == STUDIO_STORAGE_UNAVAILABLE_REASON


def test_legacy_video_tos_config_remains_a_compatibility_fallback(
    monkeypatch,
) -> None:
    monkeypatch.delenv("VEADK_STUDIO_TOS_BUCKET", raising=False)
    monkeypatch.delenv("VEADK_STUDIO_TOS_REGION", raising=False)
    monkeypatch.setenv("VEADK_VIDEO_ASSET_STORAGE", "tos")
    monkeypatch.setenv("VEADK_VIDEO_TOS_BUCKET", "legacy-bucket")
    monkeypatch.setenv("VEADK_VIDEO_TOS_REGION", "cn-beijing")
    monkeypatch.setenv("VEADK_VIDEO_TOS_ENDPOINT", "legacy.example.com")

    config = StudioStorageConfig.from_env("volcengine")

    assert config.configured is True
    assert config.bucket == "legacy-bucket"
    assert config.region == "cn-beijing"
    assert config.endpoint == "legacy.example.com"


def test_studio_object_key_is_user_first_and_url_encodes_unsafe_user_ids() -> None:
    ref = MediaRef(
        app_name="video",
        user_id="user/example name",
        session_id="reference_image",
        media_id="asset-1",
    )

    assert studio_object_key(ref, "content") == (
        f"{STUDIO_STORAGE_ROOT_PREFIX}/users/user%2Fexample%20name/"
        "video/reference_image/asset-1/content"
    )
