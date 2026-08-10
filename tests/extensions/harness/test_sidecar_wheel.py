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

import shutil
import subprocess
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


@pytest.fixture(scope="module")
def sidecar_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    repository_root = Path(__file__).resolve().parents[3]
    build_root = tmp_path_factory.mktemp("sidecar-wheel-source")
    for filename in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copy2(repository_root / filename, build_root / filename)
    shutil.copytree(
        repository_root / "veadk",
        build_root / "veadk",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )

    destination = build_root / "dist"
    uv = shutil.which("uv")
    assert uv is not None, "uv is required to verify the release wheel"
    completed = subprocess.run(
        [
            uv,
            "build",
            "--wheel",
            "--out-dir",
            str(destination),
            "--no-build-logs",
            "--no-create-gitignore",
            ".",
        ],
        cwd=build_root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    wheels = list(destination.glob("*.whl"))
    assert len(wheels) == 1
    return wheels[0]


def test_wheel_owns_sidecar_runtime_without_sdk_namespace_overlap(
    sidecar_wheel: Path,
) -> None:
    with ZipFile(sidecar_wheel) as archive:
        names = set(archive.namelist())

    runtime_prefix = "veadk/extensions/harness/sidecar_runtime/"
    expected_modules = {
        "__init__.py",
        "component_catalog.py",
        "deploy.py",
        "failover_proxy.py",
        "profiles.py",
        "runtime_components.py",
        "runtime_gateway_proxy.py",
        "selection.py",
        "sidecar.py",
        "sidecar_config.py",
    }
    assert {
        name.removeprefix(runtime_prefix)
        for name in names
        if name.startswith(runtime_prefix) and name.endswith(".py")
    } == expected_modules
    assert not any(name.startswith("agentkit/") for name in names)


def test_wheel_metadata_keeps_sidecar_optional_and_sdk_081_compatible(
    sidecar_wheel: Path,
) -> None:
    with ZipFile(sidecar_wheel) as archive:
        metadata_name = next(
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        )
        metadata = BytesParser().parsebytes(archive.read(metadata_name))

    requirements = [
        Requirement(value) for value in metadata.get_all("Requires-Dist", [])
    ]
    sdk_requirements = [
        item
        for item in requirements
        if canonicalize_name(item.name) == "agentkit-sdk-python"
    ]
    assert any(
        item.marker is None and ">=0.8.0" in str(item.specifier)
        for item in sdk_requirements
    )
    sidecar_extra = [
        item
        for item in sdk_requirements
        if item.marker is not None and "harness-sidecar" in str(item.marker)
    ]
    assert len(sidecar_extra) == 1
    assert ">=0.8.1" in str(sidecar_extra[0].specifier)
    assert "<0.9.0" in str(sidecar_extra[0].specifier)

    forbidden = {
        "agentkit-harness-sidecar-integration",
        "bytedance-agentkit-harness-sidecar",
    }
    assert not (
        forbidden
        & {canonicalize_name(requirement.name) for requirement in requirements}
    )


def test_wheel_does_not_add_a_standalone_sidecar_cli(sidecar_wheel: Path) -> None:
    with ZipFile(sidecar_wheel) as archive:
        entry_points_name = next(
            name
            for name in archive.namelist()
            if name.endswith(".dist-info/entry_points.txt")
        )
        entry_points = archive.read(entry_points_name).decode("utf-8")

    assert "agentkit-harness-sidecar" not in entry_points
