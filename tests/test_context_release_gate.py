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

"""Release dependency contracts prevent bypassing context regression checks."""

import ast
import json
import sys
from pathlib import Path

import pytest
import yaml
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github/workflows"


def test_python_and_studio_releases_require_context_gate():
    for filename, job in [
        ("publish-tag-to-pypi.yaml", "build"),
        ("publish-studio-release.yaml", "verify"),
    ]:
        jobs = yaml.safe_load((WORKFLOWS / filename).read_text())["jobs"]
        assert "context-compression-gate" in jobs[job]["needs"]
        gate = jobs["context-compression-gate"]
        assert gate["uses"] == "./.github/workflows/context-compression-gate.yaml"
        assert "if" not in gate and "continue-on-error" not in gate


def test_context_gate_covers_both_supported_adk_lines():
    workflow = yaml.safe_load((WORKFLOWS / "context-compression-gate.yaml").read_text())
    job = workflow["jobs"]["contracts"]
    assert set(job["strategy"]["matrix"]["adk"]) == {
        "1.34.0",
        "2.1.0",
        "2.2.0",
    }
    assert set(job["strategy"]["matrix"]["python"]) == {"3.10", "3.12"}
    assert any(
        "tests/run_context_compression_gate.py" in step.get("run", "")
        for step in job["steps"]
    )


def test_context_gate_runs_studio_contracts():
    workflow = yaml.safe_load((WORKFLOWS / "context-compression-gate.yaml").read_text())
    job = workflow["jobs"]["studio-contracts"]
    assert "if" not in job and "continue-on-error" not in job
    assert any(
        "tests/contextCompression*.test.mjs" in step.get("run", "")
        for step in job["steps"]
    )


def test_parallel_lifecycle_regressions_are_required_by_gate():
    workflow = yaml.safe_load((WORKFLOWS / "context-compression-gate.yaml").read_text())
    # PyYAML's YAML 1.1 loader interprets the GitHub Actions `on` key as True.
    triggers = workflow.get("on", workflow.get(True))
    paths = triggers["pull_request"]["paths"]
    assert "veadk/agents/**" in paths
    assert "tests/agent/**" in paths
    tree = ast.parse(
        (WORKFLOWS.parents[1] / "tests/run_context_compression_gate.py").read_text()
    )
    selected = next(
        ast.literal_eval(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "tests" for t in node.targets)
    )
    assert {
        "tests/context",
        "tests/agent/test_workflow_execution.py",
        "tests/agent/test_workflow_agent_contract.py",
        "tests/agent/test_parallel_cleanup.py",
    } <= set(selected)


def _project_and_adk_requirements():
    project = tomllib.loads((WORKFLOWS.parents[1] / "pyproject.toml").read_text())[
        "project"
    ]
    groups = {"base": project["dependencies"], **project["optional-dependencies"]}
    return project, {
        group: [r for text in values if (r := Requirement(text)).name == "google-adk"]
        for group, values in groups.items()
        if any(Requirement(text).name == "google-adk" for text in values)
    }


def _dependency_fixture():
    return json.loads(
        (
            WORKFLOWS.parents[1] / "tests/fixtures/adk_dependency_metadata.json"
        ).read_text()
    )


@pytest.mark.parametrize("version", ["1.34.0", "2.1.0", "2.2.0", "2.3.0", "2.9.2"])
def test_adk_declarations_match_published_otel_compatibility(version):
    """Reject the first incompatible release and CI badcase in base AND extras."""
    project, groups = _project_and_adk_requirements()
    exporter = next(
        Requirement(text)
        for text in project["dependencies"]
        if Requirement(text).name == "opentelemetry-exporter-otlp"
    )
    # OTLP pins SDK/API at its own version. Use that actual pin, not a test-only
    # fallback that could hide dependency drift.
    pins = list(exporter.specifier)
    assert len(pins) == 1 and pins[0].operator == "=="
    otel_version = pins[0].version
    fixture = _dependency_fixture()
    assert all(
        otel_version in Requirement(text).specifier
        for text in fixture["agentkit_sdk_python"]["otel_requirements"]
    )
    compatible = all(
        otel_version in Requirement(text).specifier
        for text in fixture["google_adk"][version]["otel_requirements"]
    )
    assert groups["base"] and groups["eval"]
    for group, requirements in groups.items():
        for requirement in requirements:
            assert (version in requirement.specifier) == compatible, (
                f"{group}: {requirement} misstates ADK {version} compatibility "
                f"with the installed OTel {otel_version} family"
            )


def test_adk_matrix_and_lock_follow_declared_support_without_bypasses():
    _, groups = _project_and_adk_requirements()
    specifier = groups["base"][0].specifier
    workflow = yaml.safe_load((WORKFLOWS / "context-compression-gate.yaml").read_text())
    job = workflow["jobs"]["contracts"]
    targets = set(job["strategy"]["matrix"]["adk"])
    metadata = _dependency_fixture()["google_adk"]
    assert targets == {version for version in metadata if version in specifier}
    lock = tomllib.loads((WORKFLOWS.parents[1] / "uv.lock").read_text())
    locked_adk = next(p for p in lock["package"] if p["name"] == "google-adk")
    assert locked_adk["version"] in targets
    locked_sdk = next(p for p in lock["package"] if p["name"] == "veadk-python")
    locked_requirements = [
        r for r in locked_sdk["metadata"]["requires-dist"] if r["name"] == "google-adk"
    ]
    assert locked_requirements
    assert all(SpecifierSet(r["specifier"]) == specifier for r in locked_requirements)
    assert "if" not in job and "continue-on-error" not in job
    runs = []
    for step in job["steps"]:
        assert "continue-on-error" not in step
        command = step.get("run", "")
        if command and "Report failure" not in step.get("name", ""):
            assert "if" not in step
            assert "--no-deps" not in command
            assert "|| true" not in command
            runs.append(command)
    assert any("pip check" in command for command in runs)
    assert any("pip install -e '.[dev]'" in command for command in runs)
    assert any("tests/run_context_compression_gate.py" in command for command in runs)
