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

"""Bootstrap the pinned AgentKit CLI before a Studio revision starts."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

from veadk.cli.agentkit_cli import (
    AGENTKIT_CLI_VERSION,
    AgentKitCliError,
    default_agentkit_cli_cache_root,
    resolve_agentkit_cli,
)
from veadk.cli.studio_artifacts import (
    StudioRuntimeManifest,
    download_studio_artifact,
)
from veadk.utils.cloud_provider import CloudProvider, normalize_cloud_provider


StudioCompanionError = AgentKitCliError


def required_agentkit_cli_version() -> str:
    """Return the immutable native CLI version owned by this VeADK release."""

    return AGENTKIT_CLI_VERSION


def validate_installed_agentkit_cli(
    *,
    archive: Path | None = None,
    runtime_manifest: Path | None = None,
    provider: CloudProvider | str | None = None,
) -> str:
    """Resolve or install the exact CLI required by Studio."""

    if archive is not None and runtime_manifest is not None:
        raise StudioCompanionError(
            "Studio must use either a local CLI archive or a runtime manifest."
        )
    resolved_provider = normalize_cloud_provider(provider) if provider else None
    if runtime_manifest is not None:
        try:
            manifest = StudioRuntimeManifest.from_json(runtime_manifest.read_bytes())
            if resolved_provider is not None and manifest.provider != resolved_provider:
                raise ValueError("Studio runtime manifest provider is invalid.")
            artifact = manifest.agentkit_cli()
            archive = download_studio_artifact(
                artifact,
                default_agentkit_cli_cache_root()
                / "studio-artifacts"
                / artifact.sha256
                / artifact.filename,
            )
        except (OSError, ValueError) as error:
            raise StudioCompanionError(str(error)) from error
    resolve_agentkit_cli(archive=archive)
    return AGENTKIT_CLI_VERSION


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--archive", type=Path)
    source.add_argument("--runtime-manifest", type=Path)
    parser.add_argument("--provider", choices=("volcengine", "byteplus"))
    return parser


def main() -> None:
    """Fail the candidate Studio revision before serving if bootstrap fails."""

    args = _parser().parse_args()
    version = validate_installed_agentkit_cli(
        archive=args.archive,
        runtime_manifest=args.runtime_manifest,
        provider=cast(CloudProvider | None, args.provider),
    )
    print(f"AgentKit CLI {version} is ready.")


if __name__ == "__main__":
    main()


__all__ = [
    "StudioCompanionError",
    "required_agentkit_cli_version",
    "validate_installed_agentkit_cli",
]
