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
import subprocess

import pytest
from pathlib import Path

from veadk.cli.mpa_p0_contract import (
    DEFAULT_COMPATIBILITY_MATRIX,
    default_matrix_path,
    load_default_matrix,
)


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "verify-mpa-p0-contract.sh"
RESOURCE_DIR = ROOT / "frontend" / "server" / "mpa" / "contracts" / "mpa-p0"
MATRIX = RESOURCE_DIR / "compatibility-matrix.json"


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


def test_default_matrix_path_is_owned_by_studio_mpa() -> None:
    assert default_matrix_path() == MATRIX
    assert MATRIX.is_file()


def test_absent_default_matrix_preserves_embedded_rules(tmp_path, monkeypatch) -> None:
    from veadk.cli import mpa_p0_contract

    monkeypatch.setattr(
        mpa_p0_contract, "default_matrix_path", lambda: tmp_path / "absent.json"
    )
    assert load_default_matrix() == DEFAULT_COMPATIBILITY_MATRIX


@pytest.mark.parametrize("content", ["invalid JSON", "[]"])
def test_malformed_present_matrix_is_not_hidden_by_fallback(
    tmp_path, monkeypatch, content
) -> None:
    from veadk.cli import mpa_p0_contract

    matrix = tmp_path / "invalid.json"
    matrix.write_text(content)
    monkeypatch.setattr(mpa_p0_contract, "default_matrix_path", lambda: matrix)
    with pytest.raises(ValueError):
        load_default_matrix()


@pytest.mark.parametrize(
    "filename", ["compatibility-matrix.json", "benchmark-report.schema.json"]
)
def test_studio_wheel_staging_carries_mpa_contract_resources(
    tmp_path, filename
) -> None:
    from frontend.service.studio_release_server.publisher import (
        stage_studio_wheel_source,
    )

    source = tmp_path / "source"
    source.mkdir()
    for filename_root in ("pyproject.toml", "README.md", "LICENSE"):
        (source / filename_root).write_text("fixture")
    (source / "veadk").mkdir()
    (source / "veadk" / "__init__.py").write_text("")
    relative = Path("frontend/server/mpa/contracts/mpa-p0") / filename
    resource = source / relative
    resource.parent.mkdir(parents=True)
    expected = (RESOURCE_DIR / filename).read_bytes()
    resource.write_bytes(expected)
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "index.html").write_text("fixture")
    destination = tmp_path / "wheel-source"
    stage_studio_wheel_source(source, assets, destination)
    assert (destination / relative).read_bytes() == expected
