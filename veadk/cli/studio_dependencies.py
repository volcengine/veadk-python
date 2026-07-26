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
import hashlib
import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StudioDependencyWheel:
    """One pinned wheel required by an offline Studio deployment."""

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


def stage_studio_dependency_wheels(
    destination: Path,
    *,
    source_dir: Path | None = None,
) -> tuple[Path, ...]:
    """Copy or download pinned wheels after verifying every checksum."""
    destination.mkdir(parents=True, exist_ok=True)
    staged: list[Path] = []
    for dependency in STUDIO_DEPENDENCY_WHEELS:
        if source_dir is None:
            with urllib.request.urlopen(dependency.url, timeout=60) as response:
                content = response.read()
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


def write_studio_dependency_manifest(destination: Path) -> None:
    """Write the pinned wheel metadata consumed by the release-server cache."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "wheels": [
            {
                "filename": dependency.filename,
                "url": dependency.url,
                "sha256": dependency.sha256,
            }
            for dependency in STUDIO_DEPENDENCY_WHEELS
        ]
    }
    destination.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    return parser


def main() -> None:
    """Download verified wheels for a prepared Studio source archive."""
    args = _parser().parse_args()
    staged = stage_studio_dependency_wheels(args.output_dir)
    if args.manifest is not None:
        write_studio_dependency_manifest(args.manifest)
    print(json.dumps({"wheels": [path.name for path in staged]}))


if __name__ == "__main__":
    main()


__all__ = [
    "STUDIO_DEPENDENCY_WHEELS",
    "StudioDependencyWheel",
    "stage_studio_dependency_wheels",
    "write_studio_dependency_manifest",
]
