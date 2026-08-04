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

from veadk.cloud.harness_app.harness_plugins import (
    build_harness_plugins_from_enhance,
    build_harness_plugins_from_headers,
    harness_env_from_enhance,
    harness_env_from_headers,
)
from veadk.cloud.harness_app.types import HarnessEnhanceOverrides


def test_harness_env_from_headers_maps_agentkit_headers():
    env = harness_env_from_headers(
        {
            "X-Harness-Enable-Context": "true",
            "X-Harness-Components": "invocation_context,response_verification",
            "X-Harness-Profile": "analysis",
            "X-Harness-Compression-Provider": "headroom",
        }
    )

    assert env == {
        "HARNESS_ENHANCE_ENABLED": "true",
        "HARNESS_COMPONENTS": "invocation_context,response_verification",
        "HARNESS_ENHANCE_COMPONENTS": "invocation_context,response_verification",
        "HARNESS_PROFILE": "analysis",
        "HARNESS_ENHANCE_PROFILE": "analysis",
        "HARNESS_COMPRESSION_PROVIDER": "headroom",
        "HARNESS_ENHANCE_COMPRESSION_PROVIDER": "headroom",
    }


def test_build_harness_plugins_from_headers_returns_empty_when_disabled():
    assert build_harness_plugins_from_headers({}) == []


def test_harness_env_from_enhance_maps_request_body_config():
    env = harness_env_from_enhance(
        HarnessEnhanceOverrides(
            enabled=True,
            components="invocation_context,compactor",
            profile="analysis",
            compression_provider="builtin",
        )
    )

    assert env == {
        "HARNESS_ENHANCE_ENABLED": "true",
        "HARNESS_COMPONENTS": "invocation_context,compactor",
        "HARNESS_ENHANCE_COMPONENTS": "invocation_context,compactor",
        "HARNESS_PROFILE": "analysis",
        "HARNESS_ENHANCE_PROFILE": "analysis",
        "HARNESS_COMPRESSION_PROVIDER": "builtin",
        "HARNESS_ENHANCE_COMPRESSION_PROVIDER": "builtin",
    }


def test_build_harness_plugins_from_enhance_returns_empty_when_disabled():
    assert build_harness_plugins_from_enhance(HarnessEnhanceOverrides()) == []
