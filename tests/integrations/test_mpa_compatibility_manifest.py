from __future__ import annotations

import json
import subprocess
from pathlib import Path

from veadk.cli.mpa_p0_contract import load_default_matrix


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "verify-mpa-p0-contract.sh"
MATRIX = ROOT / "contracts" / "mpa-p0" / "compatibility-matrix.json"


def _manifest(tmp_path: Path, **overrides: object) -> Path:
    payload: dict[str, object] = {
        "schemaVersion": 1,
        "veadkRevision": "a" * 40,
        "runtimeRevision": "b" * 40,
        "runtimeImageDigest": "sha256:" + "c" * 64,
        "mpaProfileSchemaVersion": 1,
        "agentkitSdkVersion": "0.8.5",
        "runtimeExecutionCapability": "urn:veadk:mpa:execution:v1",
        "sessionExecutionConfigSchemaVersion": 1,
        "workerProtocol": "codex",
        "workerRequiredEndpoints": [
            "/health",
            "/ready",
            "/v1/sessions",
            "/v1/sessions/{session_id}/turns",
            "/v1/sessions/{session_id}/events",
        ],
    }
    payload.update(overrides)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _run(manifest: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(RUNNER), "--manifest", str(manifest), "--matrix", str(MATRIX)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_preflight_accepts_the_p0_baseline(tmp_path: Path) -> None:
    result = _run(_manifest(tmp_path))

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "compatible"
    assert report["matrixRule"] == "p0-codex-rest-v1"


def test_embedded_matrix_matches_contract_file() -> None:
    assert load_default_matrix() == json.loads(MATRIX.read_text(encoding="utf-8"))


def test_preflight_rejects_unlisted_worker_contract_before_mutation(
    tmp_path: Path,
) -> None:
    result = _run(_manifest(tmp_path, workerProtocol="codex-v2"))

    assert result.returncode == 3
    report = json.loads(result.stdout)
    assert report["status"] == "incompatible"
    assert report["errorCode"] == "worker_protocol_incompatible"


def test_preflight_rejects_malformed_or_secret_bearing_manifest(tmp_path: Path) -> None:
    malformed = _manifest(tmp_path, runtimeImageDigest="latest")
    payload = json.loads(malformed.read_text(encoding="utf-8"))
    payload["accessKey"] = "must-not-be-accepted"
    malformed.write_text(json.dumps(payload), encoding="utf-8")

    result = _run(malformed)

    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["status"] == "invalid_manifest"
    assert "accessKey" not in result.stdout
    assert "must-not-be-accepted" not in result.stdout
