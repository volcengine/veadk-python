# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
# SPDX-License-Identifier: Apache-2.0

"""Exercise cold-start rewriting and thin publication together, without networking."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

from frontend.service.studio_release_server import offline_runtime, publisher
from veadk.cli import studio_artifacts


def _wheel(name: str, roots: tuple[str, ...]) -> tuple[str, bytes]:
    distribution = name.replace("-", "_")
    filename = f"{distribution}-1.0-py3-none-any.whl"
    metadata = f"{distribution}-1.0.dist-info"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for root in roots:
            archive.writestr(f"{root}/__init__.py", "VALUE = 1\n")
        archive.writestr(
            f"{metadata}/METADATA",
            f"Metadata-Version: 2.4\nName: {name}\nVersion: 1.0\n"
            "License-Expression: MIT\n",
        )
        archive.writestr(
            f"{metadata}/WHEEL",
            "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr(f"{metadata}/RECORD", "")
    return filename, output.getvalue()


@pytest.mark.skipif(
    sys.version_info[:2] != (3, 12),
    reason="release bytecode requires CPython 3.12",
)
@pytest.mark.parametrize("thin,tampered", [(False, False), (True, False), (True, True)])
def test_cold_start_release_preserves_public_wheel_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, thin: bool, tampered: bool
) -> None:
    source = tmp_path / "source"
    frontend = source / "frontend"
    frontend.mkdir(parents=True)
    (source / "veadk").mkdir()
    for filename in (
        "pyproject.toml",
        "README.md",
        "LICENSE",
        "frontend/package.json",
        "frontend/package-lock.json",
        "frontend/__init__.py",
        "veadk/__init__.py",
    ):
        (source / filename).write_text("", encoding="utf-8")
    # Load the real manifest contract without including it in the synthetic wheel.
    monkeypatch.setattr(
        publisher,
        "_load_studio_artifact_contract",
        lambda _root: studio_artifacts,
    )
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "index.html").write_text("Studio", encoding="utf-8")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    cli = inputs / "agentkit-linux-x64.tar.gz"
    cli.write_bytes(b"fixture-cli")
    monkeypatch.setattr(
        publisher, "_AGENTKIT_CLI_ARCHIVE_SHA256", publisher._sha256_file(cli)
    )
    originals: dict[str, bytes] = {}
    lock_entries: list[str] = []
    dependencies: list[str] = []
    for name, roots in offline_runtime._COLD_START_WHEEL_ROOTS.items():
        filename, content = _wheel(name, roots)
        originals[filename] = content
        if name == "veadk-python":
            continue
        dependencies.append(f"{name}==1.0\n")
        lock_entries.append(
            f'[[package]]\nname = "{name}"\nversion = "1.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n'
            'wheels = [{ url = "https://files.pythonhosted.org/packages/'
            f'{filename}", size = {len(content)}, '
            f'hash = "sha256:{hashlib.sha256(content).hexdigest()}" }}]\n'
        )
    (source / "uv.lock").write_text("".join(lock_entries), encoding="utf-8")
    resolutions: list[str] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        if command[1] == "build":
            target = Path(command[command.index("-o") + 1])
            filename = "veadk_python-1.0-py3-none-any.whl"
            (target / filename).write_bytes(originals[filename])
        elif command[1:3] == ["lock", "--check"]:
            pass
        elif command[1] == "export":
            Path(command[command.index("--output-file") + 1]).write_text(
                "".join(dependencies), encoding="utf-8"
            )
        elif "download" in command:
            target = Path(command[command.index("--dest") + 1])
            for filename, content in originals.items():
                if filename.startswith("veadk_python-"):
                    continue
                if tampered and filename.startswith("agentkit_sdk_python-"):
                    content += b"unexpected-download-bytes"
                (target / filename).write_bytes(content)
        elif command[1:3] == ["pip", "install"]:
            requirements = kwargs["input"]
            resolutions.append(requirements)
            for line in requirements.splitlines():
                if line.startswith("./"):
                    filename, digest = line.split(" --hash=sha256:")
                    wheel = Path(kwargs["cwd"]) / filename
                    assert publisher._sha256_file(wheel) == digest
        else:
            pytest.fail(f"Unexpected build command: {command[:3]}")
        return subprocess.CompletedProcess(command, 0)

    # The actual public-wheel validator and bytecode compiler are never mocked.
    monkeypatch.setattr(shutil, "which", lambda *_args, **_kwargs: "/fixture/uv")
    monkeypatch.setattr(subprocess, "run", run)
    output = tmp_path / "output"
    kwargs: dict[str, Any] = dict(
        source_root=source,
        output_dir=output,
        version="20260917120000",
        git_sha="a" * 40,
        changelog=("Fix thin release",),
        frontend_assets=assets,
        dependency_wheels=inputs,
        env={"PATH": "/fixture"},
        thin=thin,
    )
    if thin and tampered:
        with pytest.raises(
            publisher.StudioPublisherError, match="does not match uv.lock"
        ):
            publisher.build_studio_release(**kwargs)
        assert not list(output.glob("manifest-*.json"))
        assert not list(output.glob("runtime-artifacts-*"))
        return

    bundle, manifest = publisher.build_studio_release(**kwargs)
    assert resolutions
    with zipfile.ZipFile(bundle) as archive:
        full_lock = archive.read("studio-runtime.lock").decode()
        full_requirements = archive.read("requirements.txt").decode()
        for filename, original in originals.items():
            content = archive.read(filename)
            assert content != original
            digest = hashlib.sha256(content).hexdigest()
            assert f"./{filename} --hash=sha256:{digest}" in full_requirements
            if not filename.startswith("veadk_python-"):
                assert digest in full_lock
            with zipfile.ZipFile(io.BytesIO(content)) as wheel:
                assert any(name.endswith(".pyc") for name in wheel.namelist())
    if not thin:
        assert manifest.runtime_epoch == ""
        assert not list(output.glob("*thin*"))
        return
    artifacts = output / f"runtime-artifacts-{manifest.runtime_epoch}"
    assert len(list(artifacts.glob("*.whl"))) == len(originals) - 1
    with zipfile.ZipFile(output / "studio-bundle-20260917120000-thin.zip") as archive:
        runtime = json.loads(archive.read("studio-runtime.json"))
        thin_lock = archive.read("studio-runtime.lock").decode()
        for artifact in runtime["artifacts"]:
            if artifact["kind"] == "wheel":
                filename = artifact["filename"]
                assert (artifacts / filename).read_bytes() == originals[filename]
                assert artifact["sha256"] in thin_lock
        veadk = "veadk_python-1.0-py3-none-any.whl"
        with zipfile.ZipFile(io.BytesIO(archive.read(veadk))) as wheel:
            assert any(name.endswith(".pyc") for name in wheel.namelist())
        extracted = tmp_path / "thin-extracted"
        archive.extractall(extracted)
    assert publisher.validate_studio_bundle_dependencies(extracted) == (
        extracted / "studio-runtime.json"
    )
    publisher.validate_public_runtime_provenance(
        source, sorted(artifacts.glob("*.whl"))
    )
