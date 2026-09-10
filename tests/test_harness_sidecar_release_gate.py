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
    assert "test_legacy_runtime_recovery.py" in backend_run
    assert (
        "test_source_preserving_legacy_ops_update_reuses_exact_image_via_sdk"
        in backend_run
    )
    assert "test_release_server_agentkit_cli_pin_matches_veadk" in backend_run
    assert "test_tos_dependency_store_accepts_manifest_pinned_agentkit_cli_version" in (
        backend_run
    )
    assert "npm run test:harness-sidecar-coverage" in frontend_run
    assert "npm test" in frontend_run
    assert "BACKEND_RESULT" in aggregate_run
    assert "FRONTEND_RESULT" in aggregate_run
