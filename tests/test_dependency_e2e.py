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

"""Tests for release dependency E2E helpers."""

import importlib.util
from pathlib import Path

import yaml


def _load_dependency_e2e_module():
    module_path = Path(__file__).parents[1] / "scripts" / "check_dependency_e2e.py"
    spec = importlib.util.spec_from_file_location("check_dependency_e2e", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_policy_rejects_unbounded_google_adk_and_exact_opentelemetry_pin() -> None:
    checker = _load_dependency_e2e_module()

    violations = checker.validate_dependency_policy(
        [
            "google-adk>=2.7.0",
            "opentelemetry-exporter-otlp==1.37.0",
            "agentkit-sdk-python>=0.8.5",
        ]
    )

    assert violations == [
        "google-adk must declare an upper bound such as <3.",
        "opentelemetry-exporter-otlp must not be exact-pinned in base runtime "
        "dependencies.",
    ]


def test_policy_accepts_bounded_google_adk_and_open_opentelemetry_range() -> None:
    checker = _load_dependency_e2e_module()

    violations = checker.validate_dependency_policy(
        [
            "google-adk>=2.7.0,<3",
            "opentelemetry-exporter-otlp>=1.37.0",
            "agentkit-sdk-python>=0.8.5",
        ]
    )

    assert violations == []


def test_highest_satisfying_release_uses_declared_range() -> None:
    checker = _load_dependency_e2e_module()

    version = checker.highest_satisfying_release(
        "google-adk>=2.7.0,<3",
        ["2.6.0", "2.7.0", "2.11.0", "3.0.0", "3.0.0rc1"],
    )

    assert version == "2.11.0"


def test_highest_satisfying_release_respects_environment_marker() -> None:
    checker = _load_dependency_e2e_module()

    version = checker.highest_satisfying_release(
        "tomli>=2.0.1; python_version < '3.11'",
        ["2.0.1", "2.2.1"],
        environment={"python_version": "3.11"},
    )

    assert version is None


def test_requirement_applies_filters_inactive_environment_marker() -> None:
    checker = _load_dependency_e2e_module()

    applies = checker.requirement_applies(
        checker.Requirement("tomli>=2.0.1; python_version < '3.11'"),
        environment={"python_version": "3.11"},
    )

    assert applies is False


def test_highest_declared_bound_uses_inclusive_upper_bound() -> None:
    checker = _load_dependency_e2e_module()

    version = checker.highest_declared_bound(
        checker.Requirement("litellm>=1.83.7,<=1.83.14")
    )

    assert version == "1.83.14"


def test_highest_runtime_dependency_pins_only_checks_key_dependencies() -> None:
    checker = _load_dependency_e2e_module()

    pins = checker.highest_runtime_dependency_pins(
        [
            "google-adk==2.7.0",
            "opentelemetry-exporter-otlp==1.37.0",
            "pillow>=10.0.0",
        ],
        python=None,
    )

    assert pins == [
        "google-adk==2.7.0",
        "opentelemetry-exporter-otlp==1.37.0",
    ]


def test_declared_range_failure_message_tells_developer_what_to_fix() -> None:
    checker = _load_dependency_e2e_module()

    message = checker.declared_range_failure_message(
        ["opentelemetry-exporter-otlp==1.45.1", "fastmcp==4.1.0"]
    )

    assert "Dependency E2E failed" in message
    assert "Failing dependency pins:" in message
    assert "opentelemetry-exporter-otlp==1.45.1" in message
    assert "fastmcp==4.1.0" in message
    assert "current runtime pin" in message
    assert "Developer action:" in message


def test_publish_workflow_runs_dependency_e2e_before_upload() -> None:
    workflow_path = (
        Path(__file__).parents[1] / ".github" / "workflows" / "publish-tag-to-pypi.yaml"
    )
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    build_steps = workflow["jobs"]["build"]["steps"]
    step_names = [step.get("name") for step in build_steps]

    assert "Check runtime dependency policy" in step_names
    assert "Verify clean wheel install" in step_names
    assert "Verify high-risk dependency upgrades against runtime pins" in step_names
    clean_install_step = build_steps[step_names.index("Verify clean wheel install")]
    declared_range_step = build_steps[
        step_names.index("Verify high-risk dependency upgrades against runtime pins")
    ]
    assert clean_install_step["if"] == (
        "startsWith(github.ref, 'refs/tags/') || github.event_name == "
        "'workflow_dispatch'"
    )
    assert declared_range_step["if"] == clean_install_step["if"]
    assert step_names.index("Build wheel and source distribution") < step_names.index(
        "Verify clean wheel install"
    )
    assert step_names.index(
        "Verify high-risk dependency upgrades against runtime pins"
    ) < step_names.index("Upload distributables as artifact")


def test_dependency_policy_gate_runs_on_pull_requests_and_pushes() -> None:
    workflow_path = (
        Path(__file__).parents[1]
        / ".github"
        / "workflows"
        / "dependency-policy-gate.yaml"
    )
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    assert workflow[True] == {
        "pull_request": None,
        "push": None,
    }
    assert "dependency-policy-gate" in workflow["jobs"]
    steps = workflow["jobs"]["dependency-policy-gate"]["steps"]
    step_names = [step.get("name") for step in steps]

    assert "Check runtime dependency policy" in step_names


def test_pre_commit_runs_dependency_policy_for_pyproject_changes() -> None:
    config_path = Path(__file__).parents[1] / ".pre-commit-config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    local_repo = next(repo for repo in config["repos"] if repo["repo"] == "local")
    hook = next(
        hook for hook in local_repo["hooks"] if hook["id"] == "dependency-policy-gate"
    )

    assert hook["entry"] == "python3 scripts/check_dependency_e2e.py policy"
    assert hook["pass_filenames"] is False
    assert hook["files"] == r"^pyproject\.toml$"
