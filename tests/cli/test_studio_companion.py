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

from dataclasses import replace
import hashlib
from io import BytesIO
import os
from pathlib import Path
import stat
import tarfile
import zipfile

import pytest

from veadk.cli import agentkit_cli
from veadk.cli import studio_companion
from veadk.cli.agentkit_cli import (
    AGENTKIT_CLI_ENV,
    AGENTKIT_CLI_VERSION,
    AgentKitCliArtifact,
    AgentKitCliError,
    agentkit_cli_artifact,
    cached_agentkit_cli_path,
    download_agentkit_cli_archive,
    install_agentkit_cli,
    resolve_agentkit_cli,
)
from veadk.cli.studio_artifacts import StudioArtifact, StudioRuntimeManifest
from veadk.cli.studio_companion import (
    required_agentkit_cli_version,
    validate_installed_agentkit_cli,
)
from veadk.cli.studio_dependencies import stage_studio_agentkit_cli_archive


def _script(version: str = AGENTKIT_CLI_VERSION) -> bytes:
    return f"#!/bin/sh\necho 'ak {version}'\n".encode()


def _tar_bytes(
    artifact: AgentKitCliArtifact,
    *,
    member_name: str | None = None,
    member_type: bytes = tarfile.REGTYPE,
) -> bytes:
    output = BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        root = tarfile.TarInfo(f"{artifact.archive_root}/")
        root.type = tarfile.DIRTYPE
        root.mode = 0o755
        archive.addfile(root)
        content = _script()
        executable = tarfile.TarInfo(
            member_name or f"{artifact.archive_root}/{artifact.executable_name}"
        )
        executable.type = member_type
        executable.mode = 0o755
        if member_type == tarfile.REGTYPE:
            executable.size = len(content)
            archive.addfile(executable, BytesIO(content))
        else:
            executable.linkname = "outside"
            archive.addfile(executable)
    return output.getvalue()


def _write_test_archive(
    path: Path,
    *,
    member_name: str | None = None,
    member_type: bytes = tarfile.REGTYPE,
) -> AgentKitCliArtifact:
    base = agentkit_cli_artifact(system="Linux", machine="x86_64")
    content = _tar_bytes(base, member_name=member_name, member_type=member_type)
    path.write_bytes(content)
    return replace(base, sha256=hashlib.sha256(content).hexdigest())


def test_staged_cli_archive_is_runtime_readable_under_secure_umask(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    base = agentkit_cli_artifact(system="Linux", machine="x86_64")
    artifact = _write_test_archive(source / base.filename)
    previous_umask = os.umask(0o077)
    try:
        target = stage_studio_agentkit_cli_archive(
            destination,
            source_dir=source,
            artifact=artifact,
        )
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE(target.stat().st_mode) == 0o644


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Linux", "x86_64", "agentkit-linux-x64.tar.gz"),
        ("Linux", "aarch64", "agentkit-linux-arm64.tar.gz"),
        ("Darwin", "x86_64", "agentkit-darwin-x64.tar.gz"),
        ("Darwin", "arm64", "agentkit-darwin-arm64.tar.gz"),
        ("Windows", "AMD64", "agentkit-windows-x64.zip"),
    ],
)
def test_platform_mapping(system: str, machine: str, expected: str) -> None:
    assert agentkit_cli_artifact(system=system, machine=machine).filename == expected


def test_platform_mapping_rejects_unsupported_platform() -> None:
    with pytest.raises(AgentKitCliError, match="not available"):
        agentkit_cli_artifact(system="FreeBSD", machine="riscv64")


def test_required_version_is_owned_by_veadk_not_distribution_metadata() -> None:
    assert required_agentkit_cli_version() == "0.52.14"


def test_companion_materializes_manifest_cli_for_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel = tmp_path / "dependency.whl"
    wheel.write_bytes(b"wheel")
    archive = tmp_path / "agentkit-linux-x64.tar.gz"
    archive.write_bytes(b"cli")
    manifest = StudioRuntimeManifest.create(
        "byteplus",
        (
            StudioArtifact.from_path(wheel, provider="byteplus", kind="wheel"),
            StudioArtifact.from_path(
                archive,
                provider="byteplus",
                kind="agentkit-cli",
            ),
        ),
    )
    manifest_path = tmp_path / "studio-runtime.json"
    manifest_path.write_bytes(manifest.to_json())
    captured: dict[str, object] = {}

    def _download(artifact: StudioArtifact, destination: Path) -> Path:
        captured["artifact"] = artifact
        captured["destination"] = destination
        return archive

    def _resolve(**kwargs: object) -> Path:
        captured.update(kwargs)
        return tmp_path / "ak"

    monkeypatch.setattr(studio_companion, "download_studio_artifact", _download)
    monkeypatch.setattr(studio_companion, "resolve_agentkit_cli", _resolve)
    monkeypatch.setattr(
        studio_companion,
        "default_agentkit_cli_cache_root",
        lambda: tmp_path / "cache",
    )

    assert (
        validate_installed_agentkit_cli(
            runtime_manifest=manifest_path,
            provider="byteplus",
        )
        == AGENTKIT_CLI_VERSION
    )
    assert captured["artifact"].provider == "byteplus"  # type: ignore[union-attr]
    assert captured["archive"] == archive


def test_companion_rejects_runtime_manifest_provider_mismatch(tmp_path: Path) -> None:
    wheel = tmp_path / "dependency.whl"
    wheel.write_bytes(b"wheel")
    archive = tmp_path / "agentkit-linux-x64.tar.gz"
    archive.write_bytes(b"cli")
    manifest = StudioRuntimeManifest.create(
        "volcengine",
        (
            StudioArtifact.from_path(wheel, provider="volcengine", kind="wheel"),
            StudioArtifact.from_path(
                archive,
                provider="volcengine",
                kind="agentkit-cli",
            ),
        ),
    )
    manifest_path = tmp_path / "studio-runtime.json"
    manifest_path.write_bytes(manifest.to_json())

    with pytest.raises(AgentKitCliError, match="provider"):
        validate_installed_agentkit_cli(
            runtime_manifest=manifest_path,
            provider="byteplus",
        )


def test_install_verified_archive_and_reuse_cache(tmp_path: Path) -> None:
    archive = tmp_path / "agentkit-linux-x64.tar.gz"
    artifact = _write_test_archive(archive)
    cache = tmp_path / "cache"

    first = install_agentkit_cli(
        artifact=artifact,
        archive=archive,
        cache_root=cache,
    )
    second = install_agentkit_cli(
        artifact=artifact,
        archive=tmp_path / "missing.tar.gz",
        cache_root=cache,
    )

    assert first == second
    assert os.access(first, os.X_OK)


def test_install_replaces_corrupt_cache(tmp_path: Path) -> None:
    archive = tmp_path / "agentkit-linux-x64.tar.gz"
    artifact = _write_test_archive(archive)
    cache = tmp_path / "cache"
    executable = cached_agentkit_cli_path(artifact, cache_root=cache)
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\necho 'ak 0.1.0'\n", encoding="utf-8")
    executable.chmod(0o755)

    resolved = install_agentkit_cli(
        artifact=artifact,
        archive=archive,
        cache_root=cache,
    )

    assert resolved.read_bytes() == _script()


def test_concurrent_install_promotes_one_valid_cache(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    archive = tmp_path / "agentkit-linux-x64.tar.gz"
    artifact = _write_test_archive(archive)
    cache = tmp_path / "cache"

    def install() -> Path:
        return install_agentkit_cli(
            artifact=artifact,
            archive=archive,
            cache_root=cache,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        resolved = list(executor.map(lambda _: install(), range(2)))

    assert resolved[0] == resolved[1]
    assert resolved[0].is_file()


@pytest.mark.parametrize(
    ("member_name", "member_type", "message"),
    [
        ("../ak", tarfile.REGTYPE, "unsafe path"),
        (None, tarfile.SYMTYPE, "link or special file"),
    ],
)
def test_install_rejects_unsafe_tar_members(
    tmp_path: Path,
    member_name: str | None,
    member_type: bytes,
    message: str,
) -> None:
    archive = tmp_path / "agentkit-linux-x64.tar.gz"
    artifact = _write_test_archive(
        archive,
        member_name=member_name,
        member_type=member_type,
    )

    with pytest.raises(AgentKitCliError, match=message):
        install_agentkit_cli(
            artifact=artifact,
            archive=archive,
            cache_root=tmp_path / "cache",
        )


def test_zip_extractor_rejects_path_traversal(tmp_path: Path) -> None:
    base = agentkit_cli_artifact(system="Windows", machine="AMD64")
    archive = tmp_path / base.filename
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../ak.exe", b"binary")
    artifact = replace(base, sha256=hashlib.sha256(archive.read_bytes()).hexdigest())

    with pytest.raises(AgentKitCliError, match="unsafe path"):
        install_agentkit_cli(
            artifact=artifact,
            archive=archive,
            cache_root=tmp_path / "cache",
        )


class _Response(BytesIO):
    def __init__(
        self,
        content: bytes,
        *,
        url: str,
        length: str | None = None,
    ) -> None:
        super().__init__(content)
        self._url = url
        self.headers = {} if length is None else {"Content-Length": length}

    def geturl(self) -> str:
        return self._url


def test_download_checks_sha_and_atomically_promotes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = b"archive"
    base = agentkit_cli_artifact(system="Linux", machine="x86_64")
    artifact = replace(base, sha256=hashlib.sha256(content).hexdigest())
    monkeypatch.setattr(
        agentkit_cli,
        "_open_release_url",
        lambda url: _Response(content, url=url, length=str(len(content))),
    )
    destination = tmp_path / artifact.filename

    assert download_agentkit_cli_archive(destination, artifact) == destination
    assert destination.read_bytes() == content
    assert not list(tmp_path.glob("*.part"))


def test_download_rejects_cross_host_redirect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = agentkit_cli_artifact(system="Linux", machine="x86_64")
    monkeypatch.setattr(
        agentkit_cli,
        "_open_release_url",
        lambda _url: _Response(b"archive", url="https://example.com/archive"),
    )

    with pytest.raises(AgentKitCliError, match="pinned HTTPS release host"):
        download_agentkit_cli_archive(tmp_path / artifact.filename, artifact)


def test_download_rejects_wrong_sha_and_cleans_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = agentkit_cli_artifact(system="Linux", machine="x86_64")
    monkeypatch.setattr(
        agentkit_cli,
        "_open_release_url",
        lambda url: _Response(b"tampered", url=url),
    )

    with pytest.raises(AgentKitCliError, match="checksum"):
        download_agentkit_cli_archive(tmp_path / artifact.filename, artifact)
    assert not list(tmp_path.iterdir())


def test_interrupted_download_retries_and_cleans_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = agentkit_cli_artifact(system="Linux", machine="x86_64")
    attempts = 0

    class _InterruptedResponse(_Response):
        def read(self, size: int = -1) -> bytes:
            del size
            raise OSError("connection reset")

    def interrupted(url: str) -> _InterruptedResponse:
        nonlocal attempts
        attempts += 1
        return _InterruptedResponse(b"", url=url)

    monkeypatch.setattr(agentkit_cli, "_open_release_url", interrupted)
    monkeypatch.setattr(agentkit_cli.time, "sleep", lambda _seconds: None)

    with pytest.raises(AgentKitCliError, match="Could not download"):
        download_agentkit_cli_archive(tmp_path / artifact.filename, artifact)
    assert attempts == 3
    assert not list(tmp_path.iterdir())


def test_download_rejects_oversized_response_and_cleans_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = agentkit_cli_artifact(system="Linux", machine="x86_64")
    monkeypatch.setattr(agentkit_cli, "_MAX_ARCHIVE_BYTES", 4)
    monkeypatch.setattr(
        agentkit_cli,
        "_open_release_url",
        lambda url: _Response(b"large", url=url, length="5"),
    )

    with pytest.raises(AgentKitCliError, match="size limit"):
        download_agentkit_cli_archive(tmp_path / artifact.filename, artifact)
    assert not list(tmp_path.iterdir())


def test_explicit_cli_must_match_pinned_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "ak"
    executable.write_text("#!/bin/sh\necho 'ak 0.1.0'\n", encoding="utf-8")
    executable.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    monkeypatch.setenv(AGENTKIT_CLI_ENV, str(executable))

    with pytest.raises(AgentKitCliError, match="does not reference"):
        resolve_agentkit_cli(cache_root=tmp_path / "cache", allow_download=False)


def test_explicit_archive_overrides_stale_cli_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "agentkit-linux-x64.tar.gz"
    artifact = _write_test_archive(archive)
    stale_executable = tmp_path / "stale-ak"
    stale_executable.write_text("#!/bin/sh\necho 'ak 0.1.0'\n", encoding="utf-8")
    stale_executable.chmod(0o755)
    monkeypatch.setenv(AGENTKIT_CLI_ENV, str(stale_executable))
    monkeypatch.setattr(agentkit_cli, "agentkit_cli_artifact", lambda: artifact)

    resolved = resolve_agentkit_cli(
        archive=archive,
        cache_root=tmp_path / "cache",
        allow_download=False,
    )

    assert resolved.read_bytes() == _script()


def test_valid_explicit_cli_is_used_without_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "ak"
    executable.write_bytes(_script())
    executable.chmod(0o755)
    monkeypatch.setenv(AGENTKIT_CLI_ENV, str(executable))

    assert (
        resolve_agentkit_cli(cache_root=tmp_path / "cache", allow_download=False)
        == executable
    )


def test_explicit_archive_fails_closed_before_valid_cli_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "agentkit-linux-x64.tar.gz"
    artifact = _write_test_archive(archive)
    archive.write_bytes(b"tampered")
    executable = tmp_path / "ak"
    executable.write_bytes(_script())
    executable.chmod(0o755)
    monkeypatch.setenv(AGENTKIT_CLI_ENV, str(executable))
    monkeypatch.setattr(agentkit_cli, "agentkit_cli_artifact", lambda: artifact)

    with pytest.raises(AgentKitCliError, match="checksum"):
        resolve_agentkit_cli(
            archive=archive,
            cache_root=tmp_path / "cache",
            allow_download=False,
        )


def test_resolver_uses_valid_path_before_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "ak"
    executable.write_bytes(_script())
    executable.chmod(0o755)
    monkeypatch.setattr(agentkit_cli, "_compatible_companion_executable", lambda: None)
    monkeypatch.setattr(agentkit_cli.shutil, "which", lambda name: str(executable))

    assert (
        resolve_agentkit_cli(
            cache_root=tmp_path / "missing-cache",
            allow_download=False,
        )
        == executable
    )
