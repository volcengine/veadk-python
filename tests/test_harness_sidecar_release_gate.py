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

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


WORKFLOW = (
    Path(__file__).parents[1] / ".github/workflows/harness-sidecar-release-gate.yaml"
)


def _run_script(job: dict[str, object]) -> str:
    steps = job.get("steps")
    assert isinstance(steps, list)
    return "\n".join(
        str(step.get("run") or "") for step in steps if isinstance(step, dict)
    )


def test_sidecar_dependency_cache_and_triggers_follow_lockfile() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML's YAML 1.1 parser treats the Actions `on` key as True.
    triggers = workflow[True]
    for event in ("push", "pull_request"):
        assert {"pyproject.toml", "uv.lock"} <= set(triggers[event]["paths"])
    steps = workflow["jobs"]["backend-gate"]["steps"]
    uv_steps = [step for step in steps if "astral-sh/setup-uv@" in step.get("uses", "")]
    assert len(uv_steps) == 1
    settings = uv_steps[0]["with"]
    assert settings["enable-cache"] is True
    assert {"pyproject.toml", "uv.lock"} <= set(
        settings["cache-dependency-glob"].split()
    )


@pytest.mark.parametrize("failed_module", ["", "pytest", "coverage"])
def test_sidecar_checks_use_frozen_environment_and_propagate_failure(
    tmp_path: Path, failed_module: str
) -> None:
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"][
        "backend-gate"
    ]["steps"]
    install = next(
        step["run"]
        for step in steps
        if step.get("name") == "Install Python test dependencies"
    )
    checks = next(
        step["run"]
        for step in steps
        if step.get("name") == "Run Python Sidecar checks in parallel"
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.jsonl"
    github_path = tmp_path / "github-path"
    github_path.touch()
    # Simulate a cold runner: only the installer can create the test interpreter.
    # Never resolve dependencies or launch actual tests from this shell contract.
    uv = bin_dir / "uv"
    uv.write_text(
        f"#!{sys.executable}\n"
        "import pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "assert args[0] == 'sync' and '--frozen' in args\n"
        "assert args[args.index('--extra') + 1] == 'dev'\n"
        "target = pathlib.Path('.venv/bin/python')\n"
        "target.parent.mkdir(parents=True)\n"
        "target.write_bytes(pathlib.Path('test-python').read_bytes())\n"
        "target.chmod(0o755)\n",
        encoding="utf-8",
    )
    uv.chmod(0o755)
    system_python = bin_dir / "python"
    system_python.write_text("#!/bin/sh\nexit 97\n", encoding="utf-8")
    system_python.chmod(0o755)
    (tmp_path / "test-python").write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "assert sys.argv[1:3] in (['-m', 'pytest'], ['-m', 'coverage'])\n"
        "with open(os.environ['SIDECAR_TEST_CALLS'], 'a') as stream:\n"
        "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "sys.exit(1 if sys.argv[2] == os.environ['SIDECAR_FAILED_MODULE'] else 0)\n",
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.defpath}",
        "GITHUB_PATH": str(github_path),
        "GITHUB_WORKSPACE": str(tmp_path),
        "RUNNER_TEMP": str(tmp_path),
        "SIDECAR_TEST_CALLS": str(calls),
        "SIDECAR_FAILED_MODULE": failed_module,
    }
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", install],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    added_paths = github_path.read_text(encoding="utf-8").splitlines()
    env["PATH"] = os.pathsep.join([*added_paths, env["PATH"]])
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", checks],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == (1 if failed_module else 0), (
        result.stdout + result.stderr
    )
    commands = [json.loads(line) for line in calls.read_text().splitlines()]
    assert sum(command[:2] == ["-m", "pytest"] for command in commands) == 4
    if failed_module != "pytest":
        coverage = next(command for command in commands if command[1] == "coverage")
        assert "--fail-under=91" in coverage
    for group in ("coverage", "lifecycle", "credentials", "release"):
        assert f"::group::Python Sidecar {group}" in result.stdout


def test_sidecar_release_gate_runs_backend_and_frontend_in_parallel() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]

    assert set(jobs) == {"backend-gate", "frontend-gate", "gate"}
    backend = jobs["backend-gate"]
    frontend = jobs["frontend-gate"]
    aggregate = jobs["gate"]
    assert "needs" not in backend
    assert "needs" not in frontend
    assert backend["timeout-minutes"] == 3
    assert frontend["timeout-minutes"] == 3
    assert set(aggregate["needs"]) == {"backend-gate", "frontend-gate"}
    assert aggregate["if"] == "${{ always() }}"

    backend_run = _run_script(backend)
    frontend_run = _run_script(frontend)
    aggregate_run = _run_script(aggregate)
    assert "test_studio_sidecar.py" in backend_run
    assert "tests/cli/test_studio_startup_imports.py" in backend_run
    assert "test_deferred_veadk_builtin_tools.py" in backend_run
    assert "test_legacy_runtime_recovery.py" in backend_run
    assert "zero_mcp_servers_json" in backend_run
    assert "test_zero_structured_mcp_is_valid" in backend_run
    assert (
        "test_source_preserving_legacy_ops_update_migrates_output_repository_via_sdk"
        in backend_run
    )
    assert (
        "test_source_preserving_disabled_sidecar_contract_filters_harness_env"
        in backend_run
    )
    assert "tests/frontend/server/test_runtime_iam.py" in backend_run
    assert (
        "test_new_deployment_creates_requested_instance_range_without_republishing"
        in backend_run
    )
    assert (
        "test_sidecar_update_resolves_or_explicitly_reuses_stored_mcp_credentials"
        in (backend_run)
    )
    assert "test_release_server_agentkit_cli_pin_matches_veadk" in backend_run
    assert "tests/test_studio_release_cold_start.py" in backend_run
    assert "test_smoke_gate_survives_platform_entrypoint_mode_normalization" in (
        backend_run
    )
    assert "test_smoke_gate_requires_unexpected_studio_exit_to_fail_closed" in (
        backend_run
    )
    assert "test_smoke_gate_is_fresh_amd64_and_runs_before_import_validation" in (
        backend_run
    )
    assert "test_update_application_code_bundle_merges_only_explicit_environment" in (
        backend_run
    )
    assert "test_vefaas_deploy_updates_existing_application_in_place" in backend_run
    assert "test_release_entrypoint_parallel_startup_fails_closed" in backend_run
    assert (
        "test_from_veidentity_uses_existing_client_secret_without_client_lookup"
        in backend_run
    )
    assert (
        "test_runtime_veidentity_oauth_preflight_is_read_only_and_reuses_secret"
        in backend_run
    )
    assert "test_local_veidentity_oauth_preserves_auto_provisioning" in backend_run
    assert "test_runtime_identity_and_oauth_preflights_run_in_parallel" in backend_run
    assert (
        "test_initialized_runtime_identity_failure_blocks_studio_startup" in backend_run
    )
    assert "test_directory_normalizes_credential_resolver_failure" in backend_run
    assert "test_uninitialized_runtime_with_readable_identity_never_writes" in (
        backend_run
    )
    assert "test_missing_marker_blocks_runtime_even_after_identity_was_prepared" in (
        backend_run
    )
    assert "test_deployment_identity_migration_allows_read_only_runtime_start" in (
        backend_run
    )
    assert "test_uninitialized_runtime_blocks_before_identity_access_or_writes" in (
        backend_run
    )
    assert "test_submit_latest_uses_fixed_deployment_ids_and_sts" in backend_run
    assert (
        "test_self_update_identity_migration_failure_blocks_function_submit"
        in backend_run
    )
    assert "test_tos_dependency_store_accepts_manifest_pinned_agentkit_cli_version" in (
        backend_run
    )
    assert "npm run test:harness-sidecar-coverage" in frontend_run
    assert "npm test" in frontend_run
    assert "BACKEND_RESULT" in aggregate_run
    assert "FRONTEND_RESULT" in aggregate_run
