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

"""Build and publish immutable Studio release bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_VERSION_PATTERN = re.compile(r"^\d{14}$")
_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
STUDIO_RELEASE_REGION = "cn-beijing"
DEFAULT_RELEASE_PREFIX = "veadk/studio/main"
MAX_STUDIO_BUNDLE_BYTES = 300 * 1024 * 1024
MAX_STUDIO_RELEASES = 50


class StudioReleaseError(ValueError):
    """Raised when a Studio release is malformed or cannot be transferred."""


@dataclass(frozen=True)
class StudioReleaseManifest:
    """Metadata for one immutable Studio release bundle."""

    version: str
    git_sha: str
    sha256: str
    size: int
    created_at: str
    changelog: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        try:
            parsed_version = datetime.strptime(self.version, "%Y%m%d%H%M%S").replace(
                tzinfo=ZoneInfo("Asia/Shanghai")
            )
        except ValueError as error:
            raise StudioReleaseError(
                "Studio release version must use Beijing time YYYYMMDDHHMMSS."
            ) from error
        if not _VERSION_PATTERN.fullmatch(self.version):
            raise StudioReleaseError(
                "Studio release version must use Beijing time YYYYMMDDHHMMSS."
            )
        if parsed_version.year < 2025:
            raise StudioReleaseError(
                "Studio release version is outside the valid range."
            )
        if not _GIT_SHA_PATTERN.fullmatch(self.git_sha):
            raise StudioReleaseError("Studio release gitSha must be a 40-digit SHA.")
        if not _SHA256_PATTERN.fullmatch(self.sha256):
            raise StudioReleaseError("Studio release sha256 is invalid.")
        if self.size <= 0 or self.size > MAX_STUDIO_BUNDLE_BYTES:
            raise StudioReleaseError("Studio release bundle size is invalid.")
        try:
            datetime.fromisoformat(self.created_at)
        except ValueError as error:
            raise StudioReleaseError("Studio release createdAt is invalid.") from error
        if len(self.changelog) > 50 or any(
            not item.strip() or len(item) > 240 for item in self.changelog
        ):
            raise StudioReleaseError("Studio release changelog is invalid.")

    @classmethod
    def from_json(cls, payload: bytes | str) -> StudioReleaseManifest:
        """Parse a manifest from its TOS representation."""
        try:
            raw = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise StudioReleaseError(
                "Studio release manifest is not valid JSON."
            ) from error
        if not isinstance(raw, dict):
            raise StudioReleaseError("Studio release manifest must be a JSON object.")
        try:
            return cls(
                version=str(raw["version"]),
                git_sha=str(raw["gitSha"]),
                sha256=str(raw["sha256"]),
                size=int(raw["size"]),
                created_at=str(raw["createdAt"]),
                changelog=tuple(str(item) for item in raw.get("changelog", [])),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise StudioReleaseError(
                "Studio release manifest is missing required fields."
            ) from error

    def to_json(self) -> bytes:
        """Serialize the manifest using its public field names."""
        data = asdict(self)
        payload = {
            "version": data["version"],
            "gitSha": data["git_sha"],
            "sha256": data["sha256"],
            "size": data["size"],
            "createdAt": data["created_at"],
            "changelog": list(data["changelog"]),
        }
        return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()


def normalize_release_prefix(prefix: str) -> str:
    """Return a safe TOS object prefix without leading or trailing slashes."""
    normalized = prefix.strip().strip("/")
    if not normalized or any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise StudioReleaseError("Studio release prefix is invalid.")
    return normalized


def bundle_object_key(prefix: str, version: str) -> str:
    """Return the immutable object key for a release bundle."""
    return f"{normalize_release_prefix(prefix)}/releases/{version}/studio-bundle.zip"


def manifest_object_key(prefix: str, version: str) -> str:
    """Return the immutable object key for a release manifest."""
    return f"{normalize_release_prefix(prefix)}/releases/{version}/manifest.json"


def latest_manifest_object_key(prefix: str) -> str:
    """Return the mutable main-channel manifest object key."""
    return f"{normalize_release_prefix(prefix)}/latest.json"


def release_catalog_object_key(prefix: str) -> str:
    """Return the mutable release catalog object key."""
    return f"{normalize_release_prefix(prefix)}/releases.json"


class StudioReleaseStore:
    """Read and publish Studio releases in one configured TOS prefix."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        access_key: str,
        secret_key: str,
        session_token: str = "",
        prefix: str = DEFAULT_RELEASE_PREFIX,
        client: Any | None = None,
    ) -> None:
        if not bucket.strip():
            raise StudioReleaseError("Studio release TOS bucket is required.")
        if not region.strip():
            raise StudioReleaseError("Studio release TOS region is required.")
        if not access_key or not secret_key:
            raise StudioReleaseError("Studio release TOS credentials are required.")
        self.bucket = bucket.strip()
        self.region = region.strip()
        self.prefix = normalize_release_prefix(prefix)
        if client is not None:
            self._client = client
            return
        import tos

        self._client = tos.TosClientV2(
            access_key,
            secret_key,
            security_token=session_token or None,
            endpoint=f"tos-{self.region}.volces.com",
            region=self.region,
        )

    def latest_manifest(self) -> StudioReleaseManifest:
        """Download and validate the latest main-channel manifest."""
        response = self._client.get_object(
            bucket=self.bucket,
            key=latest_manifest_object_key(self.prefix),
        )
        return StudioReleaseManifest.from_json(_read_object(response, 64 * 1024))

    def manifest(self, version: str) -> StudioReleaseManifest:
        """Download one immutable release manifest by version."""
        _validate_release_version(version)
        response = self._client.get_object(
            bucket=self.bucket,
            key=manifest_object_key(self.prefix, version),
        )
        return StudioReleaseManifest.from_json(_read_object(response, 64 * 1024))

    def release_catalog(self) -> list[StudioReleaseManifest]:
        """Download the bounded list of selectable Studio releases."""
        response = self._client.get_object(
            bucket=self.bucket,
            key=release_catalog_object_key(self.prefix),
        )
        try:
            payload = json.loads(_read_object(response, 512 * 1024))
            raw_releases = payload["releases"]
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise StudioReleaseError("Studio release catalog is invalid.") from error
        if (
            not isinstance(raw_releases, list)
            or len(raw_releases) > MAX_STUDIO_RELEASES
        ):
            raise StudioReleaseError("Studio release catalog is invalid.")
        releases = [
            StudioReleaseManifest.from_json(json.dumps(item)) for item in raw_releases
        ]
        return sorted(releases, key=lambda item: item.version, reverse=True)

    def download_bundle(
        self,
        manifest: StudioReleaseManifest,
        destination: Path,
    ) -> None:
        """Download one bundle and verify its exact size and digest."""
        response = self._client.get_object(
            bucket=self.bucket,
            key=bundle_object_key(self.prefix, manifest.version),
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with destination.open("wb") as output:
            for chunk in response:
                size += len(chunk)
                if size > MAX_STUDIO_BUNDLE_BYTES or size > manifest.size:
                    raise StudioReleaseError(
                        "Studio release bundle exceeds its manifest size."
                    )
                digest.update(chunk)
                output.write(chunk)
        if size != manifest.size:
            raise StudioReleaseError(
                "Studio release bundle size does not match manifest."
            )
        if digest.hexdigest() != manifest.sha256:
            raise StudioReleaseError(
                "Studio release bundle checksum does not match manifest."
            )

    def publish(self, bundle: Path, manifest: StudioReleaseManifest) -> None:
        """Publish immutable objects, then move the latest pointer last."""
        if not bundle.is_file():
            raise StudioReleaseError(f"Studio release bundle does not exist: {bundle}")
        content = bundle.read_bytes()
        if len(content) != manifest.size:
            raise StudioReleaseError(
                "Studio release bundle size does not match manifest."
            )
        if hashlib.sha256(content).hexdigest() != manifest.sha256:
            raise StudioReleaseError(
                "Studio release bundle checksum does not match manifest."
            )
        manifest_bytes = manifest.to_json()
        releases = self._existing_releases()
        if any(item.version > manifest.version for item in releases):
            raise StudioReleaseError(
                "Studio release version must be newer than the published releases."
            )
        self._client.put_object(
            bucket=self.bucket,
            key=bundle_object_key(self.prefix, manifest.version),
            content=content,
            content_type="application/zip",
            forbid_overwrite=True,
        )
        self._client.put_object(
            bucket=self.bucket,
            key=manifest_object_key(self.prefix, manifest.version),
            content=manifest_bytes,
            content_type="application/json",
            forbid_overwrite=True,
        )
        releases = [item for item in releases if item.version != manifest.version]
        releases.append(manifest)
        releases.sort(key=lambda item: item.version, reverse=True)
        catalog_bytes = (
            json.dumps(
                {
                    "releases": [
                        json.loads(item.to_json())
                        for item in releases[:MAX_STUDIO_RELEASES]
                    ]
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        ).encode()
        self._client.put_object(
            bucket=self.bucket,
            key=release_catalog_object_key(self.prefix),
            content=catalog_bytes,
            content_type="application/json",
        )
        self._client.put_object(
            bucket=self.bucket,
            key=latest_manifest_object_key(self.prefix),
            content=manifest_bytes,
            content_type="application/json",
        )

    def _existing_releases(self) -> list[StudioReleaseManifest]:
        """Load the catalog, seeding it from the legacy latest pointer."""
        try:
            return self.release_catalog()
        except Exception as error:
            if not _is_not_found(error):
                raise
        try:
            return [self.latest_manifest()]
        except Exception as error:
            if _is_not_found(error):
                return []
            raise


def build_studio_release(
    *,
    source_root: Path,
    output_dir: Path,
    version: str,
    git_sha: str,
    changelog: tuple[str, ...] = (),
    frontend_assets: Path | None = None,
    dependency_wheels: Path | None = None,
) -> tuple[Path, StudioReleaseManifest]:
    """Build the full Studio function bundle from one source checkout."""
    from veadk.cli.studio_package import (
        build_frontend_assets,
        build_local_studio_requirements,
        write_studio_package,
    )

    _validate_release_identity(version, git_sha)
    source_root = source_root.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="veadk_studio_release_") as tmp:
        workspace = Path(tmp)
        resolved_frontend_assets = frontend_assets
        if resolved_frontend_assets is None:
            resolved_frontend_assets = workspace / "frontend"
            build_frontend_assets(
                source_root,
                resolved_frontend_assets,
                changelog=changelog,
            )
        elif not (resolved_frontend_assets / "index.html").is_file():
            raise StudioReleaseError(
                "Prepared Studio frontend assets contain no index.html."
            )
        package_dir = workspace / "package"
        requirements = build_local_studio_requirements(
            source_root,
            package_dir,
            frontend_assets=resolved_frontend_assets,
            dependency_wheels=dependency_wheels,
            provider="byteplus",
        )
        write_studio_package(
            package_dir,
            requirements=requirements,
            site_logo=None,
            provider=None,
        )
        bundle = output_dir / f"studio-bundle-{version}.zip"
        _zip_directory(package_dir, bundle)
    content = bundle.read_bytes()
    manifest = StudioReleaseManifest(
        version=version,
        git_sha=git_sha,
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
        created_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(
            timespec="seconds"
        ),
        changelog=changelog,
    )
    (output_dir / f"manifest-{version}.json").write_bytes(manifest.to_json())
    return bundle, manifest


def _read_object(response: Any, max_bytes: int) -> bytes:
    content = bytearray()
    for chunk in response:
        if len(content) + len(chunk) > max_bytes:
            raise StudioReleaseError("Studio release manifest is too large.")
        content.extend(chunk)
    return bytes(content)


def _validate_release_identity(version: str, git_sha: str) -> None:
    placeholder_digest = "0" * 64
    StudioReleaseManifest(
        version=version,
        git_sha=git_sha,
        sha256=placeholder_digest,
        size=1,
        created_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(
            timespec="seconds"
        ),
    )


def _validate_release_version(version: str) -> None:
    """Validate one selectable Beijing-time release version."""
    _validate_release_identity(version, "0" * 40)


def _is_not_found(error: Exception) -> bool:
    """Return whether a TOS read failed because the object does not exist."""
    return isinstance(error, KeyError) or getattr(error, "status_code", None) == 404


def _zip_directory(source: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=Path("dist/studio-release"))
    parser.add_argument("--version", required=True)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--region", default=STUDIO_RELEASE_REGION)
    parser.add_argument("--prefix", default=DEFAULT_RELEASE_PREFIX)
    parser.add_argument("--changelog", action="append", default=[])
    parser.add_argument("--frontend-assets", type=Path)
    parser.add_argument("--dependency-wheels", type=Path)
    return parser


def main() -> None:
    """Build and publish one Studio release using environment credentials."""
    args = _parser().parse_args()
    access_key = os.getenv("VOLCENGINE_ACCESS_KEY", "")
    secret_key = os.getenv("VOLCENGINE_SECRET_KEY", "")
    session_token = os.getenv("VOLCENGINE_SESSION_TOKEN", "")
    bundle, manifest = build_studio_release(
        source_root=args.source_root,
        output_dir=args.output_dir,
        version=args.version,
        git_sha=args.git_sha,
        changelog=tuple(args.changelog),
        frontend_assets=args.frontend_assets,
        dependency_wheels=args.dependency_wheels,
    )
    store = StudioReleaseStore(
        bucket=args.bucket,
        region=args.region,
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        prefix=args.prefix,
    )
    store.publish(bundle, manifest)
    print(
        json.dumps(
            {
                "version": manifest.version,
                "gitSha": manifest.git_sha,
                "sha256": manifest.sha256,
                "size": manifest.size,
                "bucket": store.bucket,
                "prefix": store.prefix,
            }
        )
    )


if __name__ == "__main__":
    main()
