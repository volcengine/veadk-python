# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

"""Runtime networking and core-extension contracts."""

from inspect import Parameter, signature

import pytest

from veadk.extensions.harness.sidecar_runtime import deploy as deploy_module
from veadk.extensions.harness.sidecar_runtime.deploy import (
    build_runtime_network,
    deploy_harness,
    to_runtime_env,
)


def test_runtime_network_is_empty_without_explicit_options():
    assert build_runtime_network() == {}
    assert build_runtime_network(subnet_ids=[]) == {}


def test_runtime_network_preserves_explicit_false():
    assert build_runtime_network(
        mode="private",
        vpc_id="vpc-example",
        subnet_ids=["subnet-example"],
        enable_shared_internet_access=False,
    ) == {
        "mode": "private",
        "vpc_id": "vpc-example",
        "subnet_ids": ["subnet-example"],
        "enable_shared_internet_access": False,
    }


def test_deploy_network_options_are_optional_keyword_only_parameters():
    parameters = signature(deploy_harness).parameters

    for name in (
        "runtime_network_mode",
        "runtime_vpc_id",
        "runtime_subnet_ids",
        "runtime_enable_shared_internet_access",
    ):
        assert parameters[name].kind is Parameter.KEYWORD_ONLY
        assert parameters[name].default is None


def test_deploy_forwards_vpc_through_generic_core_hooks(monkeypatch):
    captured = {}
    expected = object()

    def fake_core_deploy(**kwargs):
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(deploy_module, "_deploy_harness", fake_core_deploy)

    result = deploy_harness(
        "private-harness",
        runtime_vpc_id="vpc-example",
        runtime_subnet_ids=["subnet-example"],
    )

    assert result is expected
    assert captured["runtime_env_builder"] is to_runtime_env
    assert captured["cloud_config_overrides"] == {
        "runtime_network": {
            "vpc_id": "vpc-example",
            "subnet_ids": ["subnet-example"],
        }
    }


def test_deploy_without_vpc_does_not_override_cloud_config(monkeypatch):
    captured = {}

    def fake_core_deploy(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(deploy_module, "_deploy_harness", fake_core_deploy)

    deploy_harness("legacy-harness")

    assert captured["cloud_config_overrides"] is None


def test_deploy_adapts_legacy_sdk_without_replacing_sdk_files(monkeypatch):
    captured = {}
    expected = object()
    original_env_builder = deploy_module._core_deploy_module.to_runtime_env
    original_config_builder = deploy_module._core_deploy_module.build_agentkit_config

    def fake_legacy_deploy(
        name,
        path=".",
        *,
        region=None,
        access_key=None,
        secret_key=None,
        discovery_url=None,
        allowed_id=None,
        reporter=None,
        on_conflict=None,
    ):
        captured["env"] = deploy_module._core_deploy_module.to_runtime_env(
            {"sidecar": {"enabled": True, "profile": "default"}}
        )
        captured["config"] = deploy_module._core_deploy_module.build_agentkit_config(
            name,
            region or "cn-beijing",
            captured["env"],
        )
        return expected

    monkeypatch.setattr(deploy_module, "_deploy_harness", fake_legacy_deploy)

    result = deploy_harness(
        "legacy-harness",
        runtime_vpc_id="vpc-example",
        runtime_enable_shared_internet_access=False,
    )

    assert result is expected
    assert captured["env"]["HARNESS_SIDECAR_ENABLED"] == "true"
    assert captured["config"]["launch_types"]["cloud"]["runtime_network"] == {
        "vpc_id": "vpc-example",
        "enable_shared_internet_access": False,
    }
    assert deploy_module._core_deploy_module.to_runtime_env is original_env_builder
    assert (
        deploy_module._core_deploy_module.build_agentkit_config
        is original_config_builder
    )


def test_legacy_sdk_adapters_are_restored_after_failure(monkeypatch):
    original_env_builder = deploy_module._core_deploy_module.to_runtime_env
    original_config_builder = deploy_module._core_deploy_module.build_agentkit_config

    def fail_legacy_deploy(
        name,
        path=".",
        *,
        region=None,
        access_key=None,
        secret_key=None,
        discovery_url=None,
        allowed_id=None,
        reporter=None,
        on_conflict=None,
    ):
        raise RuntimeError("deploy failed")

    monkeypatch.setattr(deploy_module, "_deploy_harness", fail_legacy_deploy)

    with pytest.raises(RuntimeError, match="deploy failed"):
        deploy_harness("legacy-harness")

    assert deploy_module._core_deploy_module.to_runtime_env is original_env_builder
    assert (
        deploy_module._core_deploy_module.build_agentkit_config
        is original_config_builder
    )
