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

from pathlib import Path

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
    assert "test_legacy_runtime_recovery.py" in backend_run
    assert "zero_mcp_servers_json" in backend_run
    assert "test_zero_structured_mcp_is_valid" in backend_run
    assert (
        "test_source_preserving_legacy_ops_update_migrates_output_repository_via_sdk"
        in backend_run
    )
    assert "tests/frontend/server/test_runtime_iam.py" in backend_run
    assert "test_new_deployment_only_updates_non_default_instance_range" in backend_run
    assert (
        "test_sidecar_update_resolves_or_explicitly_reuses_stored_mcp_credentials"
        in (backend_run)
    )
    assert "test_release_server_agentkit_cli_pin_matches_veadk" in backend_run
    assert "test_smoke_gate_survives_platform_entrypoint_mode_normalization" in (
        backend_run
    )
    assert "test_smoke_gate_is_fresh_amd64_and_runs_before_import_validation" in (
        backend_run
    )
    assert "test_update_application_code_bundle_merges_only_explicit_environment" in (
        backend_run
    )
    assert "test_vefaas_deploy_updates_existing_application_in_place" in backend_run
    assert "test_tos_dependency_store_accepts_manifest_pinned_agentkit_cli_version" in (
        backend_run
    )
    assert "npm run test:harness-sidecar-coverage" in frontend_run
    assert "npm test" in frontend_run
    assert "BACKEND_RESULT" in aggregate_run
    assert "FRONTEND_RESULT" in aggregate_run
