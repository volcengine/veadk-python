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

from veadk.cli.cli_frontend import (
    _STUDIO_STORAGE_ENV_KEYS,
    _studio_storage_environment,
)


def test_video_storage_deployment_env_allowlist_is_non_secret_and_complete() -> None:
    assert set(_STUDIO_STORAGE_ENV_KEYS) == {
        "VEADK_STUDIO_TOS_BUCKET",
        "VEADK_STUDIO_TOS_REGION",
        "VEADK_VIDEO_ASSET_STORAGE",
        "VEADK_VIDEO_TOS_BUCKET",
        "VEADK_VIDEO_TOS_REGION",
        "VEADK_VIDEO_TOS_ENDPOINT",
        "VEADK_VIDEO_TOS_PREFIX",
        "VEADK_VIDEO_MAX_FILE_BYTES",
        "VEADK_MEDIA_STORAGE",
        "VEADK_MEDIA_TOS_PREFIX",
        "DATABASE_TOS_BUCKET",
        "DATABASE_TOS_REGION",
        "DATABASE_TOS_ENDPOINT",
    }
    assert all(
        "SECRET" not in key and "ACCESS_KEY" not in key
        for key in _STUDIO_STORAGE_ENV_KEYS
    )


def test_studio_storage_env_survives_the_deployment_environment_reset() -> None:
    source = {
        "VEADK_STUDIO_TOS_BUCKET": "studio-bucket",
        "VEADK_STUDIO_TOS_REGION": "cn-beijing",
        "VOLCENGINE_SECRET_KEY": "must-not-be-forwarded",
    }

    assert _studio_storage_environment(source) == {
        "VEADK_STUDIO_TOS_BUCKET": "studio-bucket",
        "VEADK_STUDIO_TOS_REGION": "cn-beijing",
    }
