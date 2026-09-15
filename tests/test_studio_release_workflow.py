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

"""Regression tests for the Studio release workflow."""

import hashlib
import io
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from typing import Any

import pytest
import yaml


def _publish_job() -> dict[str, Any]:
    workflow_path = (
        Path(__file__).parents[1]
        / ".github"
        / "workflows"
        / "publish-studio-release.yaml"
    )
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    return workflow["jobs"]["publish"]


def test_thin_bundle_input_is_scoped_to_supported_provider() -> None:
    publish = _publish_job()
    providers = {
        entry["provider"]: entry for entry in publish["strategy"]["matrix"]["include"]
    }

    assert providers["volcengine"]["thin_bundles"] == "${{ inputs.thin_bundles }}"
    assert providers["byteplus"]["thin_bundles"] is False
    assert publish["env"]["RELEASE_THIN_BUNDLES"] == "${{ matrix.thin_bundles }}"


def _verification_script() -> str:
    workflow_path = (
        Path(__file__).parents[1]
        / ".github"
        / "workflows"
        / "publish-studio-release.yaml"
    )
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    step = next(
        step
        for step in workflow["jobs"]["verify"]["steps"]
        if step.get("name") == "Build and validate Studio bundle"
    )
    return step["run"].split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]


def test_verification_reuses_checked_inputs_and_rebuilds_current_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from veadk.cli import (
        agentkit_cli,
        studio_dependencies,
        studio_package,
        studio_release,
    )

    sources = [
        SimpleNamespace(
            filename=f"dependency-{index}.tar.gz",
            url=f"https://files.pythonhosted.org/packages/dependency-{index}.tar.gz",
            sha256=hashlib.sha256(f"source-{index}".encode()).hexdigest(),
        )
        for index in range(2)
    ]
    artifact = SimpleNamespace(
        filename="agentkit-linux-x64.tar.gz",
        sha256=hashlib.sha256(b"cli").hexdigest(),
    )
    monkeypatch.setattr(studio_dependencies, "STUDIO_DEPENDENCY_SOURCES", sources)
    monkeypatch.setattr(studio_dependencies, "STUDIO_AGENTKIT_CLI_ARTIFACT", artifact)
    for name, value in {
        "GITHUB_WORKSPACE": str(tmp_path / "source"),
        "RUNNER_TEMP": str(tmp_path),
        "output_dir": str(tmp_path / "output"),
        "version": "20260910120000",
        "GITHUB_SHA": "a" * 40,
    }.items():
        monkeypatch.setenv(name, value)

    downloads: list[str] = []
    builds: list[str] = []
    frontend_builds: list[Path] = []
    barrier: Barrier | None = Barrier(4)

    def synchronize() -> None:
        if barrier is not None:
            barrier.wait(timeout=5)

    def download(url: str, *, timeout: int) -> io.BytesIO:
        downloads.append(url)
        synchronize()
        index = next(index for index, source in enumerate(sources) if source.url == url)
        return io.BytesIO(f"source-{index}".encode())

    def download_cli(target: Path, selected: Any) -> None:
        assert selected is artifact
        downloads.append(selected.filename)
        synchronize()
        target.write_bytes(b"cli")

    def build_frontend(source: Path, destination: Path, *, changelog: Any) -> None:
        frontend_builds.append(source)
        synchronize()
        destination.mkdir(exist_ok=True)
        (destination / "index.html").write_text("current frontend")

    def build_bundle(**kwargs: Any) -> tuple[Path, Any]:
        assert (kwargs["frontend_assets"] / "index.html").is_file()
        for dependency in (*sources, artifact):
            content = (kwargs["dependency_wheels"] / dependency.filename).read_bytes()
            assert hashlib.sha256(content).hexdigest() == dependency.sha256
        builds.append(kwargs["git_sha"])
        return tmp_path / "bundle.zip", SimpleNamespace(
            version=kwargs["version"],
            git_sha=kwargs["git_sha"],
            sha256="b" * 64,
            size=10,
        )

    monkeypatch.setattr("urllib.request.urlopen", download)
    monkeypatch.setattr(agentkit_cli, "download_agentkit_cli_archive", download_cli)
    monkeypatch.setattr(studio_package, "build_frontend_assets", build_frontend)
    monkeypatch.setattr(studio_release, "build_studio_release", build_bundle)
    script = _verification_script()
    exec(script, {})
    assert len(downloads) == 3

    barrier = None
    monkeypatch.setenv("GITHUB_SHA", "c" * 40)
    exec(script, {})
    assert len(downloads) == 3
    assert builds == ["a" * 40, "c" * 40]
    assert len(frontend_builds) == 2

    cached_source = tmp_path / "studio-release-inputs" / sources[0].filename
    cached_source.write_bytes(b"corrupt cache")
    exec(script, {})
    assert len(downloads) == 4
    assert downloads[-1] == sources[0].url

    cached_source.unlink()
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *a, **kw: io.BytesIO(b"corrupt")
    )
    with pytest.raises(ValueError, match="checksum mismatch"):
        exec(script, {})
    assert len(builds) == 3
    assert not cached_source.exists()
