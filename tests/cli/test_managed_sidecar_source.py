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

import pytest

from veadk.cli import managed_sidecar_source
from veadk.cli.managed_sidecar_source import (
    ManagedSidecarSourceError,
    rewrite_managed_sidecar_requirements,
    stage_managed_sidecar_veadk_source,
)


_REQUIRED_FILES = (
    "__init__.py",
    "extensions/harness/__init__.py",
    "extensions/harness/sidecar.py",
    "extensions/harness/sidecar_runtime/sidecar.py",
    "integrations/agentkit/app.py",
)


def _package(root: Path) -> Path:
    package = root / "veadk"
    for relative in _REQUIRED_FILES:
        path = package / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {relative}\n", encoding="utf-8")
    return package


def test_rewrite_uses_source_snapshot_and_pins_public_sdk() -> None:
    rewritten = rewrite_managed_sidecar_requirements(
        "\n".join(
            (
                "veadk-python[harness-sidecar]>=1.1.1",
                "agentkit_sdk_python>=0.8.0,<0.9.0",
                "agentkit-harness-sidecar-integration==0.1.0",
                "google-adk>=1.34.0",
                "",
            )
        )
    )

    assert "veadk-python" in rewritten.splitlines()[0]
    assert "veadk-python[" not in rewritten
    assert "agentkit-harness-sidecar-integration" not in rewritten
    assert rewritten.splitlines()[1] == "agentkit-sdk-python==0.8.4"
    assert rewritten.splitlines().count("agentkit-sdk-python==0.8.4") == 1
    assert "google-adk>=1.34.0" in rewritten


def test_rewrite_preserves_comments_and_rejects_missing_veadk() -> None:
    with pytest.raises(ManagedSidecarSourceError, match="requirement_missing"):
        rewrite_managed_sidecar_requirements(
            "# keep\n@local-reference\nagentkit-sdk-python==0.8.4\n"
        )

    rewritten = rewrite_managed_sidecar_requirements(
        "# keep\nveadk-python[harness-sidecar]\n"
        "agentkit-sdk-python>=0.8\nagentkit_sdk_python==0.8.4\n"
    )
    assert "# keep" in rewritten
    assert rewritten.splitlines().count("agentkit-sdk-python==0.8.4") == 1


def test_stage_copies_only_safe_runtime_source_and_rewrites_requirements(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path / "installed")
    (package / "safe.json").write_text("{}\n", encoding="utf-8")
    cache = package / "__pycache__"
    cache.mkdir()
    (cache / "module.pyc").write_bytes(b"compiled")
    (package / ".env.local").write_text("SECRET=ignored\n", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    (project / "requirements.txt").write_text(
        "veadk-python[harness-sidecar]\ngoogle-adk\n",
        encoding="utf-8",
    )

    snapshot = stage_managed_sidecar_veadk_source(
        project,
        package_dir=package,
    )

    assert snapshot.file_count == len(_REQUIRED_FILES) + 1
    assert snapshot.total_bytes > 0
    assert (project / "veadk/extensions/harness/sidecar.py").is_file()
    assert not (project / "veadk/__pycache__").exists()
    assert not (project / "veadk/.env.local").exists()
    requirements = (project / "requirements.txt").read_text(encoding="utf-8")
    assert requirements.splitlines().count("agentkit-sdk-python==0.8.4") == 1
    assert "veadk-python[" not in requirements


def test_stage_fails_closed_for_existing_target(tmp_path: Path) -> None:
    package = _package(tmp_path / "installed")
    project = tmp_path / "project"
    project.mkdir()
    (project / "requirements.txt").write_text(
        "veadk-python[harness-sidecar]\n",
        encoding="utf-8",
    )
    (project / "veadk").mkdir()

    with pytest.raises(ManagedSidecarSourceError, match="target_exists"):
        stage_managed_sidecar_veadk_source(project, package_dir=package)


def test_stage_rejects_source_symlink(tmp_path: Path) -> None:
    package = _package(tmp_path / "installed")
    (package / "linked.py").symlink_to(package / "__init__.py")
    project = tmp_path / "project"
    project.mkdir()
    (project / "requirements.txt").write_text(
        "veadk-python[harness-sidecar]\n",
        encoding="utf-8",
    )

    with pytest.raises(ManagedSidecarSourceError, match="symlink"):
        stage_managed_sidecar_veadk_source(project, package_dir=package)


def test_stage_rejects_incomplete_source_and_missing_requirements(
    tmp_path: Path,
) -> None:
    incomplete = tmp_path / "incomplete" / "veadk"
    incomplete.mkdir(parents=True)
    project = tmp_path / "project"
    project.mkdir()
    with pytest.raises(ManagedSidecarSourceError, match="source_incomplete"):
        stage_managed_sidecar_veadk_source(project, package_dir=incomplete)

    package = _package(tmp_path / "installed")
    with pytest.raises(ManagedSidecarSourceError, match="requirements_missing"):
        stage_managed_sidecar_veadk_source(project, package_dir=package)


def test_stage_rejects_sensitive_and_oversized_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _package(tmp_path / "installed")
    project = tmp_path / "project"
    project.mkdir()
    (project / "requirements.txt").write_text(
        "veadk-python[harness-sidecar]\n",
        encoding="utf-8",
    )
    (package / "private.pem").write_text("blocked\n", encoding="utf-8")
    with pytest.raises(ManagedSidecarSourceError, match="sensitive_source"):
        stage_managed_sidecar_veadk_source(project, package_dir=package)

    (package / "private.pem").unlink()
    monkeypatch.setattr(managed_sidecar_source, "_MAX_SOURCE_FILE_BYTES", 1)
    with pytest.raises(ManagedSidecarSourceError, match="file_too_large"):
        stage_managed_sidecar_veadk_source(project, package_dir=package)

    monkeypatch.setattr(
        managed_sidecar_source,
        "_MAX_SOURCE_FILE_BYTES",
        8 * 1024 * 1024,
    )
    monkeypatch.setattr(managed_sidecar_source, "_MAX_SOURCE_TOTAL_BYTES", 1)
    with pytest.raises(ManagedSidecarSourceError, match="snapshot_too_large"):
        stage_managed_sidecar_veadk_source(project, package_dir=package)
