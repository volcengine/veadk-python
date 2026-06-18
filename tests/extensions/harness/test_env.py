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

from veadk.extensions.harness.env import (
    build_harness_plugins_from_env,
    harness_enabled_from_env,
)


def test_harness_enabled_from_env():
    assert harness_enabled_from_env({"HARNESS_ENHANCE_ENABLED": "true"}) is True
    assert harness_enabled_from_env({"HARNESS_ENHANCE_ENABLED": "false"}) is False


def test_build_harness_plugins_from_env_respects_components():
    plugins = build_harness_plugins_from_env(
        {
            "HARNESS_ENHANCE_ENABLED": "true",
            "HARNESS_ENHANCE_COMPONENTS": "context_engine,hallucination",
            "HARNESS_ENHANCE_PROFILE": "analysis",
        }
    )

    assert [plugin.name for plugin in plugins] == [
        "harness_invocation_context_plugin",
        "harness_response_verification_plugin",
    ]


def test_build_harness_plugins_from_env_defaults_to_builtin_compression():
    plugins = build_harness_plugins_from_env(
        {
            "HARNESS_ENHANCE_ENABLED": "true",
            "HARNESS_ENHANCE_COMPONENTS": "compressor",
        }
    )

    assert plugins[0].name == "harness_compress_plugin"
    assert plugins[0].compressor.config.provider == "builtin"
