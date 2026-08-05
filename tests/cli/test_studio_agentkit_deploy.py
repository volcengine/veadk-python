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
from typing import Any

import pytest
import yaml

PROJECT = {
    "name": "demo_agent",
    "files": [{"path": "app.py", "content": "app = object()\n"}],
}


def test_deploy_agentkit_project_creates_runtime_with_studio_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient
    from veadk.cli.studio_agentkit_deploy import deploy_agentkit_project

    captured_config: dict[str, Any] = {}
    create_requests: list[Any] = []

    def create_runtime(_self: Any, request: Any) -> SimpleNamespace:
        create_requests.append(request)
        return SimpleNamespace(runtime_id="rt-created")

    def launch(*, config_file: str, **_kwargs: Any) -> SimpleNamespace:
        captured_config.update(yaml.safe_load(Path(config_file).read_text()))
        request = SimpleNamespace(tags=[], apmplus_enable=True, description="demo")
        created = AgentkitRuntimeClient.create_runtime(object(), request)
        return SimpleNamespace(
            success=True,
            deploy_result=SimpleNamespace(
                endpoint_url="https://runtime.example.com",
                metadata={
                    "runtime_id": created.runtime_id,
                    "runtime_name": "demo_agent",
                },
            ),
        )

    monkeypatch.setattr(AgentkitRuntimeClient, "create_runtime", create_runtime)
    monkeypatch.setattr("agentkit.toolkit.sdk.launch", launch)
    monkeypatch.setattr(
        "veadk.cli.studio_agentkit_deploy.runtime_version",
        lambda runtime_id, region: 1,
    )

    result = deploy_agentkit_project(
        project=PROJECT,
        region="cn-beijing",
        description="Created from GitHub CI/CD",
    )

    assert result["runtimeId"] == "rt-created"
    assert captured_config["common"]["agent_name"] == "demo_agent"
    assert captured_config["common"]["description"] == "Created from GitHub CI/CD"
    cloud = captured_config["launch_types"]["cloud"]
    assert cloud["region"] == "cn-beijing"
    assert "runtime_id" not in cloud
    request = create_requests[0]
    assert request.apmplus_enable is False
    assert [(tag.key, tag.value) for tag in request.tags] == [("veadk:managed", "true")]


def test_deploy_agentkit_project_reports_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.cli.studio_agentkit_deploy import deploy_agentkit_project

    events: list[str] = []

    def launch(*, config_file: str, **_kwargs: Any) -> SimpleNamespace:
        assert Path(config_file).name == "agentkit.yaml"
        return SimpleNamespace(
            success=True,
            deploy_result=SimpleNamespace(
                endpoint_url="https://runtime.example.com",
                metadata={
                    "runtime_id": "rt-created",
                    "runtime_name": "demo_agent",
                },
            ),
        )

    monkeypatch.setattr("agentkit.toolkit.sdk.launch", launch)
    monkeypatch.setattr(
        "veadk.cli.studio_agentkit_deploy.runtime_version",
        lambda runtime_id, region: 1,
    )

    deploy_agentkit_project(
        project=PROJECT,
        region="cn-beijing",
        description="Created from GitHub CI/CD",
        progress=events.append,
    )

    assert events == [
        "Writing AgentProject files...",
        "Writing agentkit.yaml...",
        "Launching AgentKit Runtime...",
        "AgentKit Runtime deployed: runtimeId=rt-created",
    ]


def test_deploy_agentkit_project_surfaces_failed_runtime_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient
    from veadk.cli.studio_agentkit_deploy import (
        StudioAgentkitDeployError,
        deploy_agentkit_project,
    )

    def create_runtime(_self: Any, _request: Any) -> SimpleNamespace:
        return SimpleNamespace(runtime_id="rt-failed")

    def launch(**_kwargs: Any) -> SimpleNamespace:
        request = SimpleNamespace(tags=[], apmplus_enable=True, description="demo")
        AgentkitRuntimeClient.create_runtime(object(), request)
        return SimpleNamespace(
            success=False,
            error="Runtime status is Error. Initialization failed",
            deploy_result=SimpleNamespace(metadata={}),
        )

    monkeypatch.setattr(AgentkitRuntimeClient, "create_runtime", create_runtime)
    monkeypatch.setattr("agentkit.toolkit.sdk.launch", launch)

    with pytest.raises(StudioAgentkitDeployError) as exc:
        deploy_agentkit_project(
            project=PROJECT,
            region="cn-beijing",
            description="Created from GitHub CI/CD",
        )

    assert str(exc.value) == "Runtime status is Error. Initialization failed"
    assert exc.value.runtime_id == "rt-failed"
    assert exc.value.phase == "deploy"


def test_deploy_agentkit_project_updates_existing_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.cli.studio_agentkit_deploy import deploy_agentkit_project

    captured: dict[str, Any] = {}

    def launch(*, config_file: str, **_kwargs: Any) -> SimpleNamespace:
        captured.update(yaml.safe_load(Path(config_file).read_text()))
        return SimpleNamespace(
            success=True,
            deploy_result=SimpleNamespace(
                endpoint_url="https://runtime.example.com",
                metadata={
                    "runtime_id": "rt-existing",
                    "runtime_name": "existing-runtime",
                },
            ),
        )

    monkeypatch.setattr("agentkit.toolkit.sdk.launch", launch)
    monkeypatch.setattr(
        "veadk.cli.studio_agentkit_deploy.get_runtime",
        lambda runtime_id, region: SimpleNamespace(
            name="existing-runtime",
            role_name="runtime-role",
            current_version_number=3,
        ),
    )

    result = deploy_agentkit_project(
        project=PROJECT,
        region="cn-beijing",
        runtime_id="rt-existing",
        description="Update from GitHub CI/CD",
    )

    assert result["runtimeId"] == "rt-existing"
    cloud = captured["launch_types"]["cloud"]
    assert cloud["runtime_id"] == "rt-existing"
    assert cloud["runtime_name"] == "existing-runtime"
    assert cloud["runtime_role_name"] == "runtime-role"
    assert cloud["image_tag"] == "veadk-v4"


def test_launch_agentkit_config_can_be_used_by_frontend_deploy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient
    from veadk.cli.studio_agentkit_deploy import launch_agentkit_config

    config_file = tmp_path / "agentkit.yaml"
    config_file.write_text("common: {}\n", encoding="utf-8")
    seen: dict[str, Any] = {}

    def create_runtime(_self: Any, request: Any) -> SimpleNamespace:
        seen["apmplus_enable"] = request.apmplus_enable
        seen["tags"] = [(tag.key, tag.value) for tag in request.tags]
        return SimpleNamespace(runtime_id="rt-frontend")

    def launch(**_kwargs: Any) -> SimpleNamespace:
        request = SimpleNamespace(tags=[], apmplus_enable=True, description="demo")
        created = AgentkitRuntimeClient.create_runtime(object(), request)
        return SimpleNamespace(
            success=True,
            deploy_result=SimpleNamespace(metadata={"runtime_id": created.runtime_id}),
        )

    monkeypatch.setattr(AgentkitRuntimeClient, "create_runtime", create_runtime)
    monkeypatch.setattr("agentkit.toolkit.sdk.launch", launch)

    result = launch_agentkit_config(
        config_file=config_file,
        runtime_tags=[
            {"Key": "veadk:managed", "Value": "true"},
            {"Key": "veadk:owner", "Value": "developer"},
        ],
    )

    assert result.success is True
    assert seen == {
        "apmplus_enable": False,
        "tags": [
            ("veadk:managed", "true"),
            ("veadk:owner", "developer"),
        ],
    }
