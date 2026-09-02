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

"""Stage the dependency wheels bundled in a Studio release."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
import hashlib
import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from veadk.cli.agentkit_cli import (
    AgentKitCliArtifact,
    agentkit_cli_artifact,
    download_agentkit_cli_archive,
    verify_agentkit_cli_archive,
)
from veadk.utils.cloud_provider import DEFAULT_CLOUD_PROVIDER, CloudProvider

_PYPI_FILE_HOST = "https://files.pythonhosted.org"
_PYPI_MIRROR_HOSTS = (
    "https://pypi.tuna.tsinghua.edu.cn",
    "https://mirrors.aliyun.com/pypi",
)
STUDIO_AGENTKIT_CLI_ARTIFACT = agentkit_cli_artifact(
    system="Linux",
    machine="x86_64",
)


@dataclass(frozen=True)
class StudioDependencyWheel:
    """One pinned wheel required by an offline Studio deployment."""

    filename: str
    url: str
    sha256: str


@dataclass(frozen=True)
class StudioDependencySource:
    """One pinned source archive built once before the FaaS offline install."""

    filename: str
    url: str
    sha256: str


STUDIO_DEPENDENCY_WHEELS = (
    StudioDependencyWheel(
        filename="trustedmcp-0.0.5-py3-none-any.whl",
        url=(
            "https://files.pythonhosted.org/packages/e0/5b/"
            "9d60a8633f4ab94c9ec0621b51a74d866086b4cb6579882fa4fb9186023b/"
            "trustedmcp-0.0.5-py3-none-any.whl"
        ),
        sha256="3e89f6c9f5fb17cb70aaaa37df21a6e01722ccb1eec6cb8fc2e61417016986d4",
    ),
    StudioDependencyWheel(
        filename="volcengine_python_sdk-5.0.36-py2.py3-none-any.whl",
        url=(
            "https://files.pythonhosted.org/packages/00/a1/"
            "9e246023bb847329bda43e516c64aa10d77b2d98c662f0e1179689020c23/"
            "volcengine_python_sdk-5.0.36-py2.py3-none-any.whl"
        ),
        sha256="3a74fa7a7baa5d5f604b175f967660cd0aa4c7057ce44d98c4041fbaf7944b5b",
    ),
    StudioDependencyWheel(
        filename=(
            "tokenizers-0.22.2-cp39-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
        ),
        url=(
            "https://files.pythonhosted.org/packages/2e/76/"
            "932be4b50ef6ccedf9d3c6639b056a967a86258c6d9200643f01269211ca/"
            "tokenizers-0.22.2-cp39-abi3-manylinux_2_17_x86_64."
            "manylinux2014_x86_64.whl"
        ),
        sha256="369cc9fc8cc10cb24143873a0d95438bb8ee257bb80c71989e3ee290e8d72c67",
    ),
    StudioDependencyWheel(
        filename="openviking_sdk-0.1.4-py3-none-any.whl",
        url=(
            "https://files.pythonhosted.org/packages/fe/af/"
            "4ca139b05f39c8ed04339d7c8aa56550df80f97d39768d2df9bd72fdbbb9/"
            "openviking_sdk-0.1.4-py3-none-any.whl"
        ),
        sha256="1e9f23332b1b687dd7f272e660953992de60ad3e9d07d62f7460fd4aedb99616",
    ),
)

BYTEPLUS_STUDIO_DEPENDENCY_WHEELS = (
    StudioDependencyWheel(
        filename="pydantic-2.12.5-py3-none-any.whl",
        url=(
            "https://files.pythonhosted.org/packages/5a/87/"
            "b70ad306ebb6f9b585f114d0ac2137d792b48be34d732d60e597c2f8465a/"
            "pydantic-2.12.5-py3-none-any.whl"
        ),
        sha256="e561593fccf61e8a20fc46dfc2dfe075b8be7d0188df33f221ad1f0139180f9d",
    ),
)


STUDIO_DEPENDENCY_SOURCES = (
    StudioDependencySource(
        filename="antlr4-python3-runtime-4.9.3.tar.gz",
        url=(
            "https://files.pythonhosted.org/packages/3e/38/"
            "7859ff46355f76f8d19459005ca000b6e7012f2f1ca597746cbcd1fbfe5e/"
            "antlr4-python3-runtime-4.9.3.tar.gz"
        ),
        sha256="f224469b4168294902bb1efa80a8bf7855f24c99aef99cbefc1bcd3cce77881b",
    ),
    StudioDependencySource(
        filename="crcmod-1.7.tar.gz",
        url=(
            "https://files.pythonhosted.org/packages/6b/b0/"
            "e595ce2a2527e169c3bcd6c33d2473c1918e0b7f6826a043ca1245dd4e5b/"
            "crcmod-1.7.tar.gz"
        ),
        sha256="dc7051a0db5f2bd48665a990d3ec1cc305a466a77358ca4492826f41f283601e",
    ),
    StudioDependencySource(
        filename="tos-2.8.7.tar.gz",
        url=(
            "https://files.pythonhosted.org/packages/fe/a6/"
            "a3345e0c789c38a48cf5a1cd0dffc69f9267735bdda6c1645bfc24fbd025/"
            "tos-2.8.7.tar.gz"
        ),
        sha256="2190d9f9e982bbd9abd6244d736770358d9ddbf8c82828af974a2e39d8ad4e57",
    ),
)


def studio_dependency_wheels(
    provider: CloudProvider = DEFAULT_CLOUD_PROVIDER,
) -> tuple[StudioDependencyWheel, ...]:
    """Return the dependency wheels to bundle for a Studio provider."""
    if provider == "byteplus":
        return STUDIO_DEPENDENCY_WHEELS + BYTEPLUS_STUDIO_DEPENDENCY_WHEELS
    return STUDIO_DEPENDENCY_WHEELS


def stage_studio_dependency_wheels(
    destination: Path,
    *,
    source_dir: Path | None = None,
    provider: CloudProvider = DEFAULT_CLOUD_PROVIDER,
    extra_wheels: Iterable[StudioDependencyWheel] = (),
) -> tuple[Path, ...]:
    """Copy or download pinned wheels after verifying every checksum."""
    destination.mkdir(parents=True, exist_ok=True)
    staged: list[Path] = []
    for dependency in studio_dependency_wheels(provider) + tuple(extra_wheels):
        if source_dir is None:
            content = _download_dependency(dependency)
        else:
            source = source_dir / dependency.filename
            if not source.is_file():
                raise ValueError(f"Missing prepared Studio wheel: {source.name}")
            content = source.read_bytes()
            if hashlib.sha256(content).hexdigest() != dependency.sha256:
                raise ValueError(f"{dependency.filename} checksum verification failed.")
        target = destination / dependency.filename
        target.write_bytes(content)
        staged.append(target)
    return tuple(staged)


def stage_studio_dependency_sources(
    destination: Path,
    *,
    source_dir: Path | None = None,
) -> tuple[Path, ...]:
    """Stage verified source-only dependencies for portable wheel creation."""
    destination.mkdir(parents=True, exist_ok=True)
    staged: list[Path] = []
    for dependency in STUDIO_DEPENDENCY_SOURCES:
        if source_dir is None:
            content = _download_dependency(dependency)
        else:
            source = source_dir / dependency.filename
            if not source.is_file():
                raise ValueError(f"Missing prepared Studio source: {source.name}")
            content = source.read_bytes()
            if hashlib.sha256(content).hexdigest() != dependency.sha256:
                raise ValueError(f"{dependency.filename} checksum verification failed.")
        target = destination / dependency.filename
        target.write_bytes(content)
        staged.append(target)
    return tuple(staged)


def stage_studio_agentkit_cli_archive(
    destination: Path,
    *,
    source_dir: Path | None = None,
    artifact: AgentKitCliArtifact = STUDIO_AGENTKIT_CLI_ARTIFACT,
) -> Path:
    """Stage the verified Linux/x64 CLI archive outside Python requirements."""

    destination.mkdir(parents=True, exist_ok=True)
    target = destination / artifact.filename
    if source_dir is None:
        download_agentkit_cli_archive(target, artifact)
    else:
        source = source_dir / artifact.filename
        if not source.is_file():
            raise ValueError(f"Missing prepared Studio artifact: {source.name}")
        verify_agentkit_cli_archive(source, artifact)
        target.write_bytes(source.read_bytes())
    verify_agentkit_cli_archive(target, artifact)
    return target


def _download_dependency(
    dependency: StudioDependencyWheel | StudioDependencySource,
) -> bytes:
    last_error: OSError | ValueError | None = None
    for url in _download_urls(dependency.url):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                content = response.read()
            if hashlib.sha256(content).hexdigest() != dependency.sha256:
                raise ValueError(f"{dependency.filename} checksum verification failed.")
            return content
        except (OSError, ValueError) as error:
            last_error = error
    if last_error is None:
        raise RuntimeError(f"{dependency.filename} has no download source.")
    raise last_error


def _download_urls(url: str) -> tuple[str, ...]:
    if not url.startswith(f"{_PYPI_FILE_HOST}/packages/"):
        return (url,)
    path = url.removeprefix(_PYPI_FILE_HOST)
    return tuple(f"{host}{path}" for host in _PYPI_MIRROR_HOSTS) + (url,)


def write_studio_dependency_manifest(destination: Path) -> None:
    """Write pinned wheel and native CLI metadata for the release-server cache."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "wheels": [
            {
                "filename": dependency.filename,
                "url": dependency.url,
                "sha256": dependency.sha256,
            }
            for dependency in studio_dependency_wheels("byteplus")
        ],
        "sources": [
            {
                "filename": dependency.filename,
                "url": dependency.url,
                "sha256": dependency.sha256,
            }
            for dependency in STUDIO_DEPENDENCY_SOURCES
        ],
        "artifacts": [
            {
                "filename": STUDIO_AGENTKIT_CLI_ARTIFACT.filename,
                "url": STUDIO_AGENTKIT_CLI_ARTIFACT.url,
                "sha256": STUDIO_AGENTKIT_CLI_ARTIFACT.sha256,
            }
        ],
    }
    destination.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--manifest-only", action="store_true")
    return parser


def main() -> None:
    """Download verified wheels for a prepared Studio source archive."""
    args = _parser().parse_args()
    if args.manifest_only:
        if args.manifest is None:
            raise SystemExit("--manifest is required with --manifest-only")
        write_studio_dependency_manifest(args.manifest)
        print(json.dumps({"manifest": str(args.manifest)}))
        return
    if args.output_dir is None:
        raise SystemExit("--output-dir is required")
    staged = stage_studio_dependency_wheels(args.output_dir)
    staged_sources = stage_studio_dependency_sources(args.output_dir)
    staged_archive = stage_studio_agentkit_cli_archive(args.output_dir)
    if args.manifest is not None:
        write_studio_dependency_manifest(args.manifest)
    print(
        json.dumps(
            {
                "wheels": [path.name for path in staged],
                "sources": [path.name for path in staged_sources],
                "artifacts": [staged_archive.name],
            }
        )
    )


if __name__ == "__main__":
    main()


__all__ = [
    "BYTEPLUS_STUDIO_DEPENDENCY_WHEELS",
    "STUDIO_AGENTKIT_CLI_ARTIFACT",
    "STUDIO_DEPENDENCY_WHEELS",
    "STUDIO_DEPENDENCY_SOURCES",
    "StudioDependencySource",
    "StudioDependencyWheel",
    "stage_studio_agentkit_cli_archive",
    "stage_studio_dependency_wheels",
    "stage_studio_dependency_sources",
    "studio_dependency_wheels",
    "write_studio_dependency_manifest",
]
