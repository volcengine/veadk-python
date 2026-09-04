# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from veadk.cli import studio_artifacts
from veadk.cli.studio_artifacts import (
    StudioArtifact,
    StudioBundledArtifact,
    StudioRuntimeManifest,
    download_studio_artifact,
)


def _artifact(
    tmp_path: Path,
    filename: str,
    content: bytes,
    *,
    provider: str = "volcengine",
    kind: str = "wheel",
) -> StudioArtifact:
    path = tmp_path / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return StudioArtifact.from_path(path, provider=provider, kind=kind)  # type: ignore[arg-type]


def _manifest(tmp_path: Path, provider: str = "volcengine") -> StudioRuntimeManifest:
    return StudioRuntimeManifest.create(
        provider=provider,  # type: ignore[arg-type]
        artifacts=(
            _artifact(
                tmp_path, "dependency-1.0-py3-none-any.whl", b"wheel", provider=provider
            ),
            _artifact(
                tmp_path,
                "agentkit-linux-x64.tar.gz",
                b"cli",
                provider=provider,
                kind="agentkit-cli",
            ),
        ),
    )


def test_runtime_epoch_is_provider_independent(tmp_path: Path) -> None:
    volcengine = _manifest(tmp_path / "volcengine", "volcengine")
    byteplus = _manifest(tmp_path / "byteplus", "byteplus")

    assert volcengine.runtime_epoch == byteplus.runtime_epoch
    assert volcengine.to_json() != byteplus.to_json()
    assert StudioRuntimeManifest.from_json(volcengine.to_json()) == volcengine


def test_runtime_manifest_tracks_private_bundled_wheels(tmp_path: Path) -> None:
    cli = _artifact(
        tmp_path,
        "agentkit-linux-x64.tar.gz",
        b"cli",
        kind="agentkit-cli",
    )
    private_wheel = tmp_path / "private_dependency-1.0-py3-none-any.whl"
    private_wheel.write_bytes(b"private")
    manifest = StudioRuntimeManifest.create(
        "volcengine",
        (cli,),
        (StudioBundledArtifact.from_path(private_wheel),),
    )

    restored = StudioRuntimeManifest.from_json(manifest.to_json())

    assert restored == manifest
    assert "./bundled-wheelhouse/private_dependency-1.0-py3-none-any.whl" in (
        manifest.remote_requirements()
    )


def test_manifest_generates_exact_remote_requirements(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    wheel = next(item for item in manifest.artifacts if item.kind == "wheel")

    assert manifest.remote_requirements() == (
        f"--no-index\n{wheel.url}#sha256={wheel.sha256}\n"
    )
    assert manifest.agentkit_cli().kind == "agentkit-cli"


def test_manifest_requires_wheel_and_unique_cli(tmp_path: Path) -> None:
    wheel = _artifact(tmp_path, "dependency.whl", b"wheel")
    cli = _artifact(
        tmp_path,
        "agentkit-linux-x64.tar.gz",
        b"cli",
        kind="agentkit-cli",
    )
    second_cli = _artifact(tmp_path, "other.tar.gz", b"other", kind="agentkit-cli")

    with pytest.raises(ValueError, match="incomplete"):
        StudioRuntimeManifest.create("volcengine", (wheel,))
    with pytest.raises(ValueError, match="incomplete"):
        StudioRuntimeManifest.create("volcengine", (wheel, cli, second_cli))


def test_manifest_rejects_coerced_fields_and_unsafe_filenames(tmp_path: Path) -> None:
    payload = json.loads(_manifest(tmp_path).to_json())
    payload["artifacts"][0]["size"] = str(payload["artifacts"][0]["size"])

    with pytest.raises(ValueError, match="invalid"):
        StudioRuntimeManifest.from_json(json.dumps(payload))
    with pytest.raises(ValueError, match="filename"):
        _artifact(tmp_path, "unsafe\nname.whl", b"wheel")


def test_download_is_atomic_and_digest_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = _artifact(tmp_path, "dependency.whl", b"verified")

    class _Response(io.BytesIO):
        headers = {"Content-Length": str(artifact.size)}

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *_args: object) -> None:
            self.close()

        def geturl(self) -> str:
            return artifact.url

    monkeypatch.setattr(
        studio_artifacts.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _Response(b"verified"),
    )
    destination = tmp_path / "cache" / artifact.filename

    assert download_studio_artifact(artifact, destination) == destination
    assert destination.read_bytes() == b"verified"
    assert not list(destination.parent.glob("*.part"))

    monkeypatch.setattr(
        studio_artifacts.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _Response(b"tampered"),
    )
    with pytest.raises(ValueError, match="checksum"):
        download_studio_artifact(artifact, tmp_path / "bad.whl")
