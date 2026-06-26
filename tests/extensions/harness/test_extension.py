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

from veadk.extensions.harness import HarnessExtension


def test_harness_extension_builds_runner_plugins() -> None:
    plugins = HarnessExtension(
        components=["invocation_context", "compactor", "response_verification"],
        profile="test",
    ).plugins()

    assert [plugin.name for plugin in plugins] == [
        "harness_invocation_context_plugin",
        "harness_compress_plugin",
        "harness_response_verification_plugin",
    ]


def test_harness_extension_from_env_respects_disabled_default() -> None:
    assert HarnessExtension.from_env({}).plugins() == []


def test_harness_extension_from_env_builds_configured_plugins() -> None:
    plugins = HarnessExtension.from_env(
        {
            "HARNESS_ENHANCE_ENABLED": "true",
            "HARNESS_ENHANCE_COMPONENTS": "invocation_context",
        }
    ).plugins()

    assert [plugin.name for plugin in plugins] == ["harness_invocation_context_plugin"]
