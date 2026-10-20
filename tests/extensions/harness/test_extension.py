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

import subprocess
import sys

from veadk.extensions.harness import HarnessExtension
from veadk.extensions.harness.sidecar import ManagedHarnessSidecar


def test_harness_extension_keeps_enabled_constructor_default() -> None:
    plugins = HarnessExtension().plugins()

    assert [plugin.name for plugin in plugins] == [
        "harness_invocation_context_plugin",
        "harness_compress_plugin",
        "harness_response_verification_plugin",
    ]


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


def test_sidecar_mode_uses_private_runtime_without_python_plugins(monkeypatch) -> None:
    monkeypatch.setattr(ManagedHarnessSidecar, "start", lambda self: None)

    extension = HarnessExtension(sidecar={"enabled": True}, profile="ops")

    assert extension.plugins() == []
    assert extension.config.enabled is False
    assert extension.config.components == []
    assert extension.sidecar.plan.activation_targets.veadk_plugins == [
        "invocation_context",
        "compactor",
        "response_verification",
        "long_run_control",
    ]
    assert extension.sidecar.plan.activation_targets.model_proxy.components == [
        "context_engine",
        "compressor",
        "verifier",
        "long_run_control",
    ]
    assert extension.sidecar.plan.activation_targets.runtime_components == [
        "harness_core",
        "ops",
        "goal_runtime",
        "model_proxy",
        "mcp_gateway",
    ]


def test_importing_sidecar_extension_does_not_import_python_plugins() -> None:
    script = """
import sys
from veadk.extensions.harness import HarnessExtension

prefix = "veadk.extensions.harness.plugins"
loaded = [name for name in sys.modules if name == prefix or name.startswith(prefix + ".")]
assert loaded == [], loaded
assert HarnessExtension is not None
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
