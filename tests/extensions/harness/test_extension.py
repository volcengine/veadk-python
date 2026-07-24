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

from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest
import tomllib

from veadk.extensions.harness import HarnessExtension


def test_harness_sidecar_dependency_is_optional_extra_only() -> None:
    pyproject = tomllib.loads(
        (Path(__file__).resolve().parents[3] / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )

    base_dependencies = pyproject["project"].get("dependencies", [])
    sidecar_extra = pyproject["project"]["optional-dependencies"]["harness-sidecar"]

    assert not any(
        "agentkit-sdk-python[harness-sidecar]" in item for item in base_dependencies
    )
    assert any("agentkit-sdk-python[harness-sidecar]" in item for item in sidecar_extra)


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


def test_default_sidecar_does_not_resolve_or_start_public_runtime(
    monkeypatch,
) -> None:
    def unexpected_start_function():
        raise AssertionError("default HarnessExtension must not start Sidecar")

    monkeypatch.setattr(
        "veadk.extensions.harness.sidecar._public_start_function",
        unexpected_start_function,
    )

    extension = HarnessExtension()

    assert extension.sidecar_status == "disabled"
    assert extension.plugins() == []


def test_explicit_enabled_keeps_plugin_only_compatibility() -> None:
    extension = HarnessExtension(enabled=True)

    assert [plugin.name for plugin in extension.plugins()] == [
        "harness_invocation_context_plugin",
        "harness_compress_plugin",
        "harness_response_verification_plugin",
    ]


def test_harness_extension_from_env_builds_configured_plugins() -> None:
    plugins = HarnessExtension.from_env(
        {
            "HARNESS_ENHANCE_ENABLED": "true",
            "HARNESS_ENHANCE_COMPONENTS": "invocation_context",
        }
    ).plugins()

    assert [plugin.name for plugin in plugins] == ["harness_invocation_context_plugin"]


def test_ops_profile_manages_sidecar_and_adds_long_run_plugin(monkeypatch) -> None:
    calls = []

    class FakeBinding:
        spec = SimpleNamespace(status="ok")
        env: ClassVar[dict[str, str]] = {
            "MODEL_AGENT_API_BASE": "http://127.0.0.1:18787/api/v3"
        }

        def stop(self) -> None:
            calls.append("stop")

    def fake_start(config, **kwargs):
        calls.append((config, kwargs))
        return FakeBinding()

    monkeypatch.setattr(
        "veadk.extensions.harness.sidecar._public_start_function",
        lambda: fake_start,
    )

    extension = HarnessExtension(
        profile="ops",
        sidecar={"mcp_gateway": {"presets": ["sql_readonly"]}},
    )
    try:
        assert extension.sidecar_status == "ok"
        assert extension.sidecar_env["MODEL_AGENT_API_BASE"].startswith("http://")
        assert calls[0][1]["profile"] == "ops"
        assert calls[0][1]["apply_env"] is True
        assert [plugin.name for plugin in extension.plugins()][-1] == (
            "harness_long_run_control_plugin"
        )
    finally:
        extension.close()

    assert calls[-1] == "stop"


def test_sidecar_startup_can_fail_open(monkeypatch) -> None:
    def fail_start(*_args, **_kwargs):
        raise RuntimeError("runtime unavailable")

    monkeypatch.setattr(
        "veadk.extensions.harness.sidecar._public_start_function",
        lambda: fail_start,
    )

    extension = HarnessExtension(sidecar={"enabled": True, "fail_open": True})

    assert extension.sidecar_status == "degraded"
    assert extension.plugins()


def test_product_component_overrides_drive_veadk_plugins(monkeypatch) -> None:
    class FakeBinding:
        spec = SimpleNamespace(status="ok")
        env: ClassVar[dict[str, str]] = {}

        def stop(self) -> None:
            pass

    monkeypatch.setattr(
        "veadk.extensions.harness.sidecar._public_start_function",
        lambda: lambda *_args, **_kwargs: FakeBinding(),
    )

    extension = HarnessExtension(
        profile="ops",
        sidecar={
            "enabled": True,
            "component_overrides": {
                "verifier": False,
                "long_run_control": False,
            },
        },
    )
    try:
        assert [plugin.name for plugin in extension.plugins()] == [
            "harness_invocation_context_plugin",
            "harness_compress_plugin",
        ]
    finally:
        extension.close()


def test_sidecar_env_switch_activates_plan_without_legacy_enhance_switch(
    monkeypatch,
) -> None:
    class FakeBinding:
        spec = SimpleNamespace(status="ok")
        env: ClassVar[dict[str, str]] = {}

        def stop(self) -> None:
            pass

    monkeypatch.setattr(
        "veadk.extensions.harness.sidecar._public_start_function",
        lambda: lambda *_args, **_kwargs: FakeBinding(),
    )

    extension = HarnessExtension.from_env(
        {"HARNESS_SIDECAR_ENABLED": "true", "HARNESS_PROFILE": "ops"}
    )
    try:
        assert [plugin.name for plugin in extension.plugins()] == [
            "harness_invocation_context_plugin",
            "harness_compress_plugin",
            "harness_response_verification_plugin",
            "harness_long_run_control_plugin",
        ]
    finally:
        extension.close()


def test_sidecar_rejects_legacy_component_namespace() -> None:
    with pytest.raises(ValueError, match="component_overrides"):
        HarnessExtension(sidecar=True, components=["compactor"])
