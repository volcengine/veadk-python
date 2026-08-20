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

import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from veadk.extensions.harness import sidecar


def test_default_harness_import_keeps_sidecar_runtime_dormant_until_used() -> None:
    script = """
import sys
import veadk.extensions.harness as harness

module_name = "veadk.extensions.harness.sidecar_runtime"
assert module_name not in sys.modules
assert "HarnessSidecarConfig" in harness.__all__
assert harness.HarnessSidecarConfig.__module__.startswith(module_name)
assert module_name in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_sidecar_runtime_api_uses_local_import_contract() -> None:
    from veadk.extensions.harness import sidecar_runtime

    assert sidecar._sidecar_runtime_api() is sidecar_runtime


def test_agentkit_cli_resolver_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    def resolve(arguments: list[str]) -> dict[str, Any]:
        captured.extend(arguments)
        return {
            "valid": True,
            "errors": [],
            "warnings": [],
            "effective_components": ["verifier"],
            "auto_added_components": [],
            "activation_targets": {
                "model_proxy": {"components": ["verifier"]},
                "mcp_gateway": {"enabled": False},
            },
            "catalog_version": "2026.07.1",
            "plan_hash": "hash-v1",
        }

    monkeypatch.setattr(sidecar, "_run_agentkit_cli_json", resolve)
    result = sidecar.resolve_studio_harness_sidecar_selection(
        {"componentOverrides": {"verifier": True}}
    )
    assert result["planHash"] == "hash-v1"
    assert captured[captured.index("--profile") + 1] == "default"
    components = [
        captured[index + 1]
        for index, argument in enumerate(captured[:-1])
        if argument == "--component"
    ]
    assert "verifier=true" in components
    assert all(not item.startswith("sql_readonly=") for item in components)

    captured.clear()
    sidecar.resolve_studio_harness_sidecar_selection(
        {
            "profile": "ops",
            "componentOverrides": {"mcp_resilience": True},
        }
    )
    assert captured[captured.index("--profile") + 1] == "ops"

    monkeypatch.setattr(sidecar, "_run_agentkit_cli_json", lambda _arguments: [])
    with pytest.raises(sidecar.HarnessSidecarDependencyError, match="invalid"):
        sidecar.resolve_studio_harness_sidecar_selection(
            {"componentOverrides": {"verifier": True}}
        )


def test_studio_intent_accepts_models_and_preserves_public_identity() -> None:
    intent = sidecar.StudioHarnessIntent(
        enabled=False,
        profile="default",
        component_overrides={
            item: False for item in sidecar.STUDIO_HARNESS_COMPONENT_IDS
        },
    )
    assert sidecar.normalize_studio_harness_intent(intent) is intent

    class Model:
        def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
            return {
                "component_overrides": {"compressor": True},
                "catalog_version": " catalog-v1 ",
                "plan_hash": " hash-v1 ",
            }

    normalized = sidecar.normalize_studio_harness_intent(Model())
    assert normalized.enabled is True
    assert normalized.catalog_version == "catalog-v1"
    assert normalized.plan_hash == "hash-v1"
    assert sidecar.studio_harness_intent_payload(normalized) == {
        "enabled": True,
        "profile": "default",
        "componentOverrides": normalized.component_overrides,
        "catalogVersion": "catalog-v1",
        "planHash": "hash-v1",
    }


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (object(), "must be an object"),
        ({"profile": "unknown"}, "profile"),
        ({"componentOverrides": []}, "must be an object"),
        ({"componentOverrides": {"verifier": "yes"}}, "must be boolean"),
    ],
)
def test_studio_intent_rejects_invalid_shapes(value: Any, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        sidecar.normalize_studio_harness_intent(value)

    class InvalidModel:
        def model_dump(self, **_kwargs: Any) -> list[str]:
            return []

    with pytest.raises(TypeError, match="serialize"):
        sidecar.normalize_studio_harness_intent(InvalidModel())


def test_catalog_is_fixed_metadata_and_does_not_load_runtime_integration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sidecar,
        "_sidecar_runtime_api",
        lambda: pytest.fail("option metadata must not load the runtime integration"),
    )
    catalog = sidecar.get_studio_harness_sidecar_catalog()
    assert [item["id"] for item in catalog["components"]] == list(
        sidecar.STUDIO_HARNESS_COMPONENT_IDS
    )
    component = catalog["components"][-1]
    assert component["displayName"] == "MCP 稳定性治理"
    assert component["description"].endswith("默认包含 SQL 只读保护。")
    assert component["dependencies"] == []
    assert component["availability"] == {
        "available": True,
        "status": "integrated",
        "reason": None,
        "minRuntimeVersion": None,
        "regions": [],
    }


def test_selected_plan_failures_env_examples_and_catalog_pin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def invalid_resolve(arguments: list[str]) -> dict[str, Any]:
        calls.append(arguments)
        return {
            "valid": False,
            "errors": ["invalid selection"],
            "catalog_version": "catalog-v1",
            "plan_hash": "hash-v1",
        }

    monkeypatch.setattr(sidecar, "_run_agentkit_cli_json", invalid_resolve)
    selected = {
        "componentOverrides": {"verifier": True},
        "catalogVersion": "catalog-v1",
    }
    with pytest.raises(ValueError, match="invalid selection"):
        sidecar.studio_harness_deployment_config(selected)
    with pytest.raises(ValueError, match="invalid selection"):
        sidecar.studio_harness_runtime_env(selected, transport="local")
    calls_before_example = len(calls)
    example = sidecar.studio_harness_env_example(selected)
    assert example["HARNESS_SIDECAR_ENABLED"] == "true"
    assert len(calls) == calls_before_example
    assert calls[0][calls[0].index("--catalog-version") + 1] == "catalog-v1"

    class ValidApi:
        sidecar_config_to_env = staticmethod(lambda *_args, **_kwargs: {})

    monkeypatch.setattr(sidecar, "_sidecar_runtime_api", ValidApi)
    monkeypatch.setattr(
        sidecar,
        "_run_agentkit_cli_json",
        lambda _arguments: {
            "valid": True,
            "errors": [],
            "warnings": [],
            "effective_components": ["verifier"],
            "auto_added_components": [],
            "activation_targets": {
                "model_proxy": {"components": ["verifier"]},
                "mcp_gateway": {"enabled": False},
            },
            "catalog_version": "catalog-v1",
            "plan_hash": "hash-v1",
        },
    )
    env, _plan = sidecar.studio_harness_runtime_env(selected, transport="local")
    assert env["HARNESS_SIDECAR_EXPECTED_PLAN_HASH"] == "hash-v1"
    example = sidecar.studio_harness_env_example(selected)
    assert example["HARNESS_SIDECAR_ENABLED"] == "true"
    assert '"verifier":true' in example["HARNESS_SIDECAR_COMPONENT_OVERRIDES"]


class _Plan:
    def __init__(self, *, valid: bool = True) -> None:
        self.valid = valid
        self.errors = ["invalid runtime plan"]
        self.plan_hash = "sha256:runtime"


class _RuntimeConfig:
    def __init__(self, plan: _Plan | None = None) -> None:
        self.resolved_plan = plan or _Plan()


def test_runtime_config_public_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[Any] = []

    class Config:
        @staticmethod
        def from_env(values: Any) -> str:
            captured.append(values)
            return "config"

    api = SimpleNamespace(
        HarnessSidecarConfig=Config,
        resolve_sidecar_config=lambda value, *, profile: _RuntimeConfig(),
        start_harness_sidecar=lambda *args, **kwargs: "started",
    )
    monkeypatch.setattr(sidecar, "_sidecar_runtime_api", lambda: api)
    assert sidecar.sidecar_config_from_env({}) is False
    values = {"HARNESS_SIDECAR_ENABLED": " yes "}
    assert sidecar.sidecar_config_from_env(values) == "config"
    assert captured == [values]
    assert sidecar.resolve_sidecar_plan(False, profile="default") is None
    assert sidecar.resolve_sidecar_plan({"enabled": False}, profile="default") is None
    assert (
        sidecar.resolve_sidecar_plan(True, profile="default").plan_hash
        == "sha256:runtime"
    )
    assert sidecar._public_start_function()(True) == "started"

    api.resolve_sidecar_config = lambda *_args, **_kwargs: _RuntimeConfig(
        _Plan(valid=False)
    )
    with pytest.raises(ValueError, match="invalid runtime plan"):
        sidecar.resolve_sidecar_plan(True, profile="default")

    api.HarnessSidecarConfig = object()
    with pytest.raises(sidecar.HarnessSidecarDependencyError, match="incompatible"):
        sidecar.sidecar_config_from_env({"HARNESS_SIDECAR_ENABLED": "true"})
    del api.resolve_sidecar_config
    with pytest.raises(sidecar.HarnessSidecarDependencyError, match="incompatible"):
        sidecar.resolve_sidecar_plan(True, profile="default")
    del api.start_harness_sidecar
    with pytest.raises(sidecar.HarnessSidecarDependencyError, match="incompatible"):
        sidecar._public_start_function()


def test_normalize_runtime_config_shapes() -> None:
    assert sidecar.normalize_sidecar_config(None) is False
    assert sidecar.normalize_sidecar_config(True) is True
    assert sidecar.normalize_sidecar_config({"enabled": True}) == {"enabled": True}

    class Model:
        def model_dump(self, **_kwargs: Any) -> dict[str, bool]:
            return {"enabled": True}

    assert sidecar.normalize_sidecar_config(Model()) == {"enabled": True}

    class InvalidModel:
        def model_dump(self, **_kwargs: Any) -> list[str]:
            return []

    with pytest.raises(TypeError, match="serialize"):
        sidecar.normalize_sidecar_config(InvalidModel())
    with pytest.raises(TypeError, match="bool, mapping"):
        sidecar.normalize_sidecar_config(object())


def test_managed_sidecar_lifecycle_and_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _Plan()
    monkeypatch.setattr(sidecar, "resolve_sidecar_plan", lambda *args, **kwargs: plan)
    stopped: list[bool] = []
    binding = SimpleNamespace(
        spec=SimpleNamespace(status="ready", plan_hash="sha256:binding"),
        env={"MODEL_AGENT_API_BASE": "http://127.0.0.1"},
        stop=lambda: stopped.append(True),
    )
    starts: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def start(*args: Any, **kwargs: Any) -> Any:
        starts.append((args, kwargs))
        return binding

    monkeypatch.setattr(sidecar, "_public_start_function", lambda: start)
    binding_env: dict[str, str] = {}
    managed = sidecar.ManagedHarnessSidecar(
        {"enabled": True, "fail_open": False},
        profile="default",
        process_env={"CUSTOMER": "kept"},
        binding_env=binding_env,
    )
    assert managed.enabled is True
    assert managed.fail_open is False
    assert managed.status == "not_started"
    assert managed.env == {}
    assert managed.plan_hash == "sha256:runtime"
    assert managed.start() is binding
    assert managed.start() is binding
    assert managed.status == "ready"
    assert managed.env == binding.env
    assert managed.plan_hash == "sha256:binding"
    assert starts[0][1] == {
        "profile": "default",
        "apply_env": True,
        "environ": binding_env,
        "process_env": {"CUSTOMER": "kept"},
    }
    managed.close()
    assert stopped == [True]
    assert managed.binding is None

    disabled = sidecar.ManagedHarnessSidecar(False)
    assert disabled.enabled is False
    assert disabled.status == "disabled"
    assert disabled.start() is None
    disabled.close()

    object_config = SimpleNamespace(enabled=False, fail_open=False)
    assert sidecar.ManagedHarnessSidecar(object_config).enabled is False


def test_managed_sidecar_failure_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sidecar, "resolve_sidecar_plan", lambda *args, **kwargs: _Plan()
    )

    def fail() -> Any:
        def start(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("sanitized startup failure")

        return start

    monkeypatch.setattr(sidecar, "_public_start_function", fail)
    fail_open = sidecar.ManagedHarnessSidecar({"enabled": True})
    assert fail_open.start() is None
    assert fail_open.status == "degraded"
    assert isinstance(fail_open.error, RuntimeError)
    assert fail_open.start() is None

    fail_closed = sidecar.ManagedHarnessSidecar({"enabled": True, "fail_open": False})
    with pytest.raises(RuntimeError, match="sanitized startup failure"):
        fail_closed.start()


def test_small_normalizers_cover_empty_and_truthy_values() -> None:
    assert sidecar._optional_string(None) is None
    assert sidecar._optional_string("  ") is None
    assert sidecar._optional_string(123) == "123"
    assert sidecar._truthy(None) is False
    assert sidecar._truthy("off") is False
    assert sidecar._truthy(" ON ") is True
