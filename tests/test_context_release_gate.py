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
from pathlib import Path

import yaml

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
        "2.9.2",
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
