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
import os
from pathlib import Path
from typing import cast

from veadk.cli.agentkit_cli import (
    AGENTKIT_CLI_VERSION,
    AgentKitCliError,
    agentkit_cli_artifact,
    default_agentkit_cli_cache_root,
    resolve_agentkit_cli,
)
from veadk.cli.studio_artifacts import (
    StudioRuntimeManifest,
    download_studio_artifact,
)
from veadk.utils.cloud_provider import CloudProvider, normalize_cloud_provider


StudioCompanionError = AgentKitCliError
STUDIO_AGENTKIT_CLI_ARCHIVE_ENV = "VEADK_STUDIO_AGENTKIT_CLI_ARCHIVE"
STUDIO_AGENTKIT_CLI_RUNTIME_MANIFEST_ENV = "VEADK_STUDIO_AGENTKIT_CLI_RUNTIME_MANIFEST"
_STUDIO_RELEASE_VERSION_ENV = "VEADK_STUDIO_RELEASE_VERSION"
_STUDIO_RUNTIME_MANIFEST_FILENAME = "studio-runtime.json"


def required_agentkit_cli_version() -> str:
    """Return the immutable native CLI version owned by this VeADK release."""

    return AGENTKIT_CLI_VERSION


def _discover_legacy_entrypoint_source() -> tuple[Path | None, Path | None]:
    """Find a Bundle source when an older updater rewrote the new entrypoint."""

    if not os.getenv(_STUDIO_RELEASE_VERSION_ENV, "").strip():
        return None, None
    current = Path.cwd()
    roots = (current, current.parent) if current.name == "output" else (current,)
    archive_name = agentkit_cli_artifact(
        system="Linux",
        machine="x86_64",
    ).filename
    archives = {
        candidate.resolve()
        for root in roots
        for candidate in (root / archive_name,)
        if candidate.is_file() and not candidate.is_symlink()
    }
    manifests = {
        candidate.resolve()
        for root in roots
        for candidate in (root / _STUDIO_RUNTIME_MANIFEST_FILENAME,)
        if candidate.is_file() and not candidate.is_symlink()
    }
    if len(archives) + len(manifests) > 1:
        raise StudioCompanionError(
            "Studio must use either a local CLI archive or a runtime manifest."
        )
    return next(iter(archives), None), next(iter(manifests), None)


def resolve_studio_managed_agentkit_cli(
    *,
    archive: Path | None = None,
    runtime_manifest: Path | None = None,
    provider: CloudProvider | str | None = None,
    cache_root: Path | None = None,
) -> Path | None:
    """Resolve the exact Bundle-owned CLI source shared by Studio processes."""

    if archive is None and runtime_manifest is None:
        archive_value = os.getenv(STUDIO_AGENTKIT_CLI_ARCHIVE_ENV, "").strip()
        manifest_value = os.getenv(
            STUDIO_AGENTKIT_CLI_RUNTIME_MANIFEST_ENV,
            "",
        ).strip()
        archive = Path(archive_value) if archive_value else None
        runtime_manifest = Path(manifest_value) if manifest_value else None
        if archive is None and runtime_manifest is None:
            archive, runtime_manifest = _discover_legacy_entrypoint_source()
    if archive is not None and runtime_manifest is not None:
        raise StudioCompanionError(
            "Studio must use either a local CLI archive or a runtime manifest."
        )
    if archive is None and runtime_manifest is None:
        return None

    resolved_provider = normalize_cloud_provider(provider) if provider else None
    if runtime_manifest is not None:
        if resolved_provider is None:
            configured_provider = (
                os.getenv("CLOUD_PROVIDER", "").strip()
                or os.getenv("AGENTKIT_CLOUD_PROVIDER", "").strip()
            )
            if configured_provider:
                resolved_provider = normalize_cloud_provider(configured_provider)
        try:
            manifest = StudioRuntimeManifest.from_json(runtime_manifest.read_bytes())
            if resolved_provider is not None and manifest.provider != resolved_provider:
                raise ValueError("Studio runtime manifest provider is invalid.")
            artifact = manifest.agentkit_cli()
            root = cache_root or default_agentkit_cli_cache_root()
            archive = download_studio_artifact(
                artifact,
                root / "studio-artifacts" / artifact.sha256 / artifact.filename,
            )
        except (OSError, ValueError) as error:
            raise StudioCompanionError(str(error)) from error
    return resolve_agentkit_cli(archive=archive, cache_root=cache_root)


def validate_installed_agentkit_cli(
    *,
    archive: Path | None = None,
    runtime_manifest: Path | None = None,
    provider: CloudProvider | str | None = None,
) -> str:
    """Resolve or install the exact CLI required by Studio."""

    resolved = resolve_studio_managed_agentkit_cli(
        archive=archive,
        runtime_manifest=runtime_manifest,
        provider=provider,
    )
    if resolved is None:
        resolve_agentkit_cli()
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
    "STUDIO_AGENTKIT_CLI_ARCHIVE_ENV",
    "STUDIO_AGENTKIT_CLI_RUNTIME_MANIFEST_ENV",
    "StudioCompanionError",
    "required_agentkit_cli_version",
    "resolve_studio_managed_agentkit_cli",
    "validate_installed_agentkit_cli",
]
