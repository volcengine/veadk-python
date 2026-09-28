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

"""Exercise cross-version updates at the real download/extraction boundary."""

from dataclasses import replace
import hashlib
import io
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest
import yaml

from frontend.service.studio_release_server import publisher
from veadk.cli import agentkit_cli
from veadk.cli.studio_artifacts import StudioArtifact, StudioRuntimeManifest
from veadk.cli.studio_release import (
    StudioReleaseError,
    StudioReleaseManifest,
    StudioReleaseStore,
)
from veadk.cli.studio_self_update import (
    StudioSelfUpdater,
    StudioUpdateSettings,
    extract_studio_bundle,
)
from veadk.utils.cloud_provider import CloudProvider


CLI_NAME = "agentkit-linux-x64.tar.gz"
TARGET_CLI = b"next release native CLI"
TARGET_SHA = hashlib.sha256(TARGET_CLI).hexdigest()
WHEEL_NAME = "veadk_python-1.2.3-py3-none-any.whl"
SOURCE_NAME = "veadk/cli/agentkit_cli.py"


def _source() -> str:
    # Use the actual source shape; executing any part of it is forbidden.
    return (
        Path(agentkit_cli.__file__)
        .read_text()
        .replace(agentkit_cli.AGENTKIT_CLI_ARTIFACTS["linux-x64"].sha256, TARGET_SHA)
        + "\nraise AssertionError('downloaded code executed')\n"
    )


def _bundles(
    tmp_path: Path,
    provider: CloudProvider = "volcengine",
    *,
    cli: bytes = TARGET_CLI,
    source: str | None = None,
) -> tuple[bytes, bytes, StudioReleaseManifest]:
    wheel = io.BytesIO()
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "veadk_python-1.2.3.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: veadk-python\nVersion: 1.2.3\n",
        )
        archive.writestr(SOURCE_NAME, _source() if source is None else source)
    wheel_bytes = wheel.getvalue()
    cli_path = tmp_path / CLI_NAME
    cli_path.write_bytes(cli)
    dependency = tmp_path / "dependency-1.0-py3-none-any.whl"
    dependency.write_bytes(b"public dependency")
    runtime = StudioRuntimeManifest.create(
        provider,
        (
            StudioArtifact.from_path(dependency, provider=provider, kind="wheel"),
            StudioArtifact.from_path(cli_path, provider=provider, kind="agentkit-cli"),
        ),
    )
    wheel_requirement = (
        f"./{WHEEL_NAME} --hash=sha256:{hashlib.sha256(wheel_bytes).hexdigest()}\n"
    )
    contents = []
    for thin in (False, True):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("run.sh", "#!/bin/bash\n")
            archive.writestr(WHEEL_NAME, wheel_bytes)
            archive.writestr(
                "requirements.txt",
                (
                    runtime.remote_requirements()
                    if thin
                    else "--no-index\n--require-hashes\n"
                )
                + wheel_requirement,
            )
            if thin:
                archive.writestr("studio-runtime.json", runtime.to_json())
            else:
                archive.writestr(CLI_NAME, cli)
        contents.append(output.getvalue())
    full, thin = contents
    release = StudioReleaseManifest(
        version="20260917150000",
        git_sha="a" * 40,
        sha256=hashlib.sha256(full).hexdigest(),
        size=len(full),
        created_at="2026-09-17T15:00:00+08:00",
        runtime_epoch=runtime.runtime_epoch,
        thin_sha256=hashlib.sha256(thin).hexdigest(),
        thin_size=len(thin),
    )
    return full, thin, release


def _store(full: bytes, thin: bytes) -> StudioReleaseStore:
    # Keep the production streaming size/digest checks, replacing only TOS I/O.
    return StudioReleaseStore(
        bucket="test-releases",
        region="cn-beijing",
        access_key="test-ak",
        secret_key="test-sk",
        client=SimpleNamespace(
            get_object=lambda **kwargs: iter(
                [thin if kwargs["key"].endswith("-thin.zip") else full]
            )
        ),
    )


def _updater(provider: CloudProvider = "volcengine") -> StudioSelfUpdater:
    return StudioSelfUpdater(
        settings=StudioUpdateSettings(
            bucket="test-releases",
            deployment_region="cn-shanghai",
            prefix="veadk/studio/main",
            application_id="application-id",
            function_id="function-id",
            project="default",
            provider=provider,
        ),
        credential_resolver=lambda: ("", "", None),
        branding_logo=None,
    )


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
@pytest.mark.parametrize("mode", ["full", "thin", "fallback"])
@pytest.mark.parametrize(
    "installed_sha",
    [
        "4e76e32c60473b5037c331a7c74bb99b1c23b62eb8ce26379d3a8c41af38a64e",
        "4439d14b4be6ccb90f6eea896adf959ffef4ab4983f41e449d80c79d4cd95de3",
    ],
)
def test_update_accepts_target_cli_across_installed_versions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider: CloudProvider,
    mode: str,
    installed_sha: str,
) -> None:
    full, thin, release = _bundles(tmp_path, provider)
    monkeypatch.setattr(publisher, "_AGENTKIT_CLI_ARCHIVE_SHA256", installed_sha)
    if mode == "full":
        release = replace(release, runtime_epoch="", thin_sha256="", thin_size=0)
    probes = []

    def probe(artifact: StudioArtifact) -> None:
        probes.append(artifact.sha256)
        if mode == "fallback" and artifact.kind == "agentkit-cli":
            raise ValueError("artifact unavailable")

    monkeypatch.setattr("veadk.cli.studio_self_update.probe_studio_artifact", probe)
    selected = _updater(provider)._download_runtime_package(
        _store(full, thin), release, tmp_path
    )
    assert selected.name == ("package-thin" if mode == "thin" else "package")
    assert len(probes) == {"full": 0, "thin": 2, "fallback": 2}[mode]
    if mode != "full":
        assert TARGET_SHA in probes
    if mode != "thin":
        assert (selected / CLI_NAME).read_bytes() == TARGET_CLI
    # The builder must still reject a CLI that differs from its own source pin.
    with pytest.raises(publisher.StudioPublisherError):
        publisher.validate_studio_bundle_dependencies(selected)


@pytest.mark.parametrize("thin", [False, True])
def test_update_rejects_cli_mismatched_with_target_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, thin: bool
) -> None:
    full, thin_bytes, _ = _bundles(tmp_path, cli=b"different CLI")
    # An archive matching the installed CLI is still wrong for this target.
    monkeypatch.setattr(
        publisher,
        "_AGENTKIT_CLI_ARCHIVE_SHA256",
        hashlib.sha256(b"different CLI").hexdigest(),
    )
    archive = tmp_path / "bundle.zip"
    archive.write_bytes(thin_bytes if thin else full)
    with pytest.raises(StudioReleaseError, match="checksum|dependency contract"):
        extract_studio_bundle(archive, tmp_path / "package")


@pytest.mark.parametrize("mutation", ["digest", "size"])
def test_update_checks_release_manifest_before_target_contract(
    tmp_path: Path, mutation: str
) -> None:
    full, thin, release = _bundles(tmp_path)
    release = replace(release, runtime_epoch="", thin_sha256="", thin_size=0)
    release = replace(
        release,
        **({"sha256": "0" * 64} if mutation == "digest" else {"size": len(full) + 1}),
    )
    with pytest.raises(StudioReleaseError, match="manifest"):
        _updater()._download_runtime_package(_store(full, thin), release, tmp_path)
    assert not (tmp_path / "package").exists()


@pytest.mark.parametrize(
    "source",
    [
        "",
        "AGENTKIT_CLI_ARTIFACTS = load_from_network()",
        "AGENTKIT_CLI_ARTIFACTS = {}",
        "not valid python!",
    ],
)
def test_update_rejects_missing_or_dynamic_target_cli_contract(
    tmp_path: Path, source: str
) -> None:
    full, _, _ = _bundles(tmp_path, source=source)
    archive = tmp_path / "bundle.zip"
    archive.write_bytes(full)
    with pytest.raises(StudioReleaseError, match="CLI contract"):
        extract_studio_bundle(archive, tmp_path / "package")


@pytest.mark.parametrize(
    "mutation", ["computed", "duplicate", "unpacked", "filename", "digest", "oversized"]
)
def test_update_rejects_ambiguous_target_cli_contract(
    tmp_path: Path, mutation: str
) -> None:
    source = _source()
    if mutation == "computed":
        source = source.replace(f'"{TARGET_SHA}"', "compute_digest()", 1)
    elif mutation == "duplicate":
        source += "\nAGENTKIT_CLI_ARTIFACTS = {}\n"
    elif mutation == "unpacked":
        source = source.replace(
            '"linux-x64": AgentKitCliArtifact(',
            '**more_artifacts, "linux-x64": AgentKitCliArtifact(',
            1,
        )
    elif mutation == "filename":
        source = source.replace(CLI_NAME, "another.tar.gz")
    elif mutation == "digest":
        source = source.replace(TARGET_SHA, "not-a-digest")
    else:
        source += "\n#" + "x" * (256 * 1024)
    full, _, _ = _bundles(tmp_path, source=source)
    archive = tmp_path / "bundle.zip"
    archive.write_bytes(full)
    with pytest.raises(StudioReleaseError, match="CLI contract"):
        extract_studio_bundle(archive, tmp_path / "package")


@pytest.mark.parametrize(
    "workflow_name,job",
    [
        ("publish-studio-release.yaml", "verify"),
        ("harness-sidecar-release-gate.yaml", "backend-gate"),
    ],
)
def test_cross_version_regression_is_required_by_release_gates(
    workflow_name: str, job: str
) -> None:
    root = Path(__file__).parents[2]
    test_file = Path(__file__).relative_to(root).as_posix()
    workflow = yaml.safe_load((root / ".github/workflows" / workflow_name).read_text())
    assert test_file in workflow[True]["pull_request"]["paths"]
    commands = "\n".join(step.get("run", "") for step in workflow["jobs"][job]["steps"])
    assert test_file in commands
