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

"""Build and publish a Studio bundle without importing the VeADK package."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from email.parser import BytesParser
from email.policy import default as email_policy
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

if __package__:
    from .offline_runtime import build_studio_offline_runtime
else:
    _offline_runtime_path = Path(__file__).with_name("offline_runtime.py")
    _offline_runtime_spec = importlib.util.spec_from_file_location(
        "veadk_studio_offline_runtime",
        _offline_runtime_path,
    )
    if _offline_runtime_spec is None or _offline_runtime_spec.loader is None:
        raise RuntimeError("Studio offline runtime builder is unavailable.")
    _offline_runtime = importlib.util.module_from_spec(_offline_runtime_spec)
    _offline_runtime_spec.loader.exec_module(_offline_runtime)
    build_studio_offline_runtime = _offline_runtime.build_studio_offline_runtime

_VERSION_PATTERN = re.compile(r"^\d{14}$")
_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MAX_STUDIO_BUNDLE_BYTES = 300 * 1024 * 1024
_MAX_STUDIO_RELEASES = 50
_AGENTKIT_CLI_ARCHIVE = "agentkit-linux-x64.tar.gz"
_AGENTKIT_CLI_ARCHIVE_SHA256 = (
    "4e76e32c60473b5037c331a7c74bb99b1c23b62eb8ce26379d3a8c41af38a64e"
)
_STUDIO_RELEASE_CONTRACT = "agentkit-cli-v1"
_STUDIO_RUNTIME_MANIFEST = "studio-runtime.json"
_PUBLIC_RUNTIME_LICENSES = frozenset(
    {
        "0BSD",
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "CC0-1.0",
        "CNRI-Python",
        "ISC",
        "MIT",
        "MIT-0",
        "MIT-CMU",
        "MPL-2.0",
        "PSF-2.0",
        "Python-2.0",
        "Unicode-3.0",
        "Unlicense",
        "Zlib",
    }
)
_PUBLIC_RUNTIME_LICENSE_CLASSIFIERS = {
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
    "License :: OSI Approved :: BSD License": "BSD-3-Clause",
    "License :: OSI Approved :: ISC License (ISCL)": "ISC",
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "License :: OSI Approved :: Python Software Foundation License": "PSF-2.0",
    "License :: OSI Approved :: The Unlicense (Unlicense)": "Unlicense",
    "License :: Public Domain": "Unlicense",
}
_PUBLIC_RUNTIME_LEGACY_LICENSES = {
    "apache 2 0": "Apache-2.0",
    "apache license 2 0": "Apache-2.0",
    "apache software license": "Apache-2.0",
    "bsd": "BSD-3-Clause",
    "bsd 2 clause": "BSD-2-Clause",
    "bsd 3 clause": "BSD-3-Clause",
    "isc": "ISC",
    "mit": "MIT",
    "mit license": "MIT",
    "mpl 2 0": "MPL-2.0",
    "mozilla public license 2 0": "MPL-2.0",
    "psf": "PSF-2.0",
    "python software foundation license": "PSF-2.0",
    "the unlicense": "Unlicense",
    "unlicense": "Unlicense",
    "zlib": "Zlib",
    "3 clause bsd license": "BSD-3-Clause",
    "bsd public domain": "BSD-3-Clause OR Unlicense",
    "bsd 3 clause apache 2 0 dependency licenses": "BSD-3-Clause OR Apache-2.0",
}


class StudioPublisherError(ValueError):
    """Raised when a Studio release cannot be built or published."""


@dataclass(frozen=True)
class StudioReleaseManifest:
    """Public metadata for one immutable Studio release bundle."""

    version: str
    git_sha: str
    sha256: str
    size: int
    created_at: str
    changelog: tuple[str, ...] = ()
    runtime_epoch: str = ""
    thin_sha256: str = ""
    thin_size: int = 0

    def __post_init__(self) -> None:
        try:
            parsed_version = datetime.strptime(self.version, "%Y%m%d%H%M%S").replace(
                tzinfo=ZoneInfo("Asia/Shanghai")
            )
        except ValueError as error:
            raise StudioPublisherError(
                "Studio release version must use Beijing time YYYYMMDDHHMMSS."
            ) from error
        if not _VERSION_PATTERN.fullmatch(self.version) or parsed_version.year < 2025:
            raise StudioPublisherError(
                "Studio release version must use Beijing time YYYYMMDDHHMMSS."
            )
        if not _GIT_SHA_PATTERN.fullmatch(self.git_sha):
            raise StudioPublisherError("Studio release gitSha must be a 40-digit SHA.")
        if not _SHA256_PATTERN.fullmatch(self.sha256):
            raise StudioPublisherError("Studio release sha256 is invalid.")
        if self.size <= 0 or self.size > _MAX_STUDIO_BUNDLE_BYTES:
            raise StudioPublisherError("Studio release bundle size is invalid.")
        try:
            datetime.fromisoformat(self.created_at)
        except ValueError as error:
            raise StudioPublisherError(
                "Studio release createdAt is invalid."
            ) from error
        if len(self.changelog) > 50 or any(
            not item.strip() or len(item) > 240 for item in self.changelog
        ):
            raise StudioPublisherError("Studio release changelog is invalid.")
        thin_values = (self.runtime_epoch, self.thin_sha256, self.thin_size)
        if any(thin_values):
            if (
                not _SHA256_PATTERN.fullmatch(self.runtime_epoch)
                or not _SHA256_PATTERN.fullmatch(self.thin_sha256)
                or self.thin_size <= 0
                or self.thin_size > _MAX_STUDIO_BUNDLE_BYTES
            ):
                raise StudioPublisherError("Studio thin release metadata is invalid.")

    @classmethod
    def from_json(cls, payload: bytes | str) -> StudioReleaseManifest:
        try:
            raw = json.loads(payload)
            return cls(
                version=str(raw["version"]),
                git_sha=str(raw["gitSha"]),
                sha256=str(raw["sha256"]),
                size=int(raw["size"]),
                created_at=str(raw["createdAt"]),
                changelog=tuple(str(item) for item in raw.get("changelog", [])),
                runtime_epoch=str(raw.get("runtimeEpoch", "")),
                thin_sha256=str(raw.get("thinSha256", "")),
                thin_size=int(raw.get("thinSize", 0) or 0),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise StudioPublisherError("Studio release manifest is invalid.") from error

    def to_json(self) -> bytes:
        data = asdict(self)
        payload = {
            "version": data["version"],
            "gitSha": data["git_sha"],
            "sha256": data["sha256"],
            "size": data["size"],
            "createdAt": data["created_at"],
            "changelog": list(data["changelog"]),
        }
        if self.runtime_epoch:
            payload.update(
                {
                    "runtimeEpoch": self.runtime_epoch,
                    "thinSha256": self.thin_sha256,
                    "thinSize": self.thin_size,
                }
            )
        return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()


def _normalize_prefix(prefix: str) -> str:
    normalized = prefix.strip().strip("/")
    if not normalized or any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise StudioPublisherError("Studio release prefix is invalid.")
    return normalized


def _bundle_key(prefix: str, version: str) -> str:
    return f"{prefix}/releases/{version}/studio-bundle.zip"


def _manifest_key(prefix: str, version: str) -> str:
    return f"{prefix}/releases/{version}/manifest.json"


def _thin_bundle_key(prefix: str, version: str) -> str:
    return f"{prefix}/releases/{version}/studio-bundle-thin.zip"


def _latest_key(prefix: str) -> str:
    return f"{prefix}/latest.json"


def _catalog_key(prefix: str) -> str:
    return f"{prefix}/releases.json"


def _read_object(response: Any, max_bytes: int) -> bytes:
    content = bytearray()
    for chunk in response:
        if len(content) + len(chunk) > max_bytes:
            raise StudioPublisherError("Studio release manifest is too large.")
        content.extend(chunk)
    return bytes(content)


def _is_not_found(error: Exception) -> bool:
    return isinstance(error, KeyError) or getattr(error, "status_code", None) == 404


class StudioReleaseStore:
    """Publish immutable release objects and move the latest pointer last."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        access_key: str,
        secret_key: str,
        session_token: str,
        prefix: str,
        provider: str = "volcengine",
    ) -> None:
        import tos

        self._bucket = bucket
        self._prefix = _normalize_prefix(prefix)
        self._client = tos.TosClientV2(
            access_key,
            secret_key,
            security_token=session_token or None,
            endpoint=(
                f"tos-{region}.bytepluses.com"
                if provider == "byteplus"
                else f"tos-{region}.volces.com"
            ),
            region=region,
        )

    def publish(
        self,
        bundle: Path,
        manifest: StudioReleaseManifest,
        *,
        thin_bundle: Path | None = None,
    ) -> None:
        """Publish immutable content and repair an identical interrupted attempt."""

        content = bundle.read_bytes()
        if (
            len(content) != manifest.size
            or hashlib.sha256(content).hexdigest() != manifest.sha256
        ):
            raise StudioPublisherError(
                "Studio release bundle does not match its manifest."
            )
        thin_content: bytes | None = None
        if manifest.runtime_epoch:
            if thin_bundle is None or not thin_bundle.is_file():
                raise StudioPublisherError("Studio thin release bundle is missing.")
            thin_content = thin_bundle.read_bytes()
            if (
                len(thin_content) != manifest.thin_size
                or hashlib.sha256(thin_content).hexdigest() != manifest.thin_sha256
            ):
                raise StudioPublisherError(
                    "Studio thin bundle does not match manifest."
                )
        elif thin_bundle is not None:
            raise StudioPublisherError("Studio full release has no thin bundle.")
        releases = self._existing_releases()
        same_version = [item for item in releases if item.version == manifest.version]
        if same_version and same_version != [manifest]:
            raise StudioPublisherError("Studio release version has a conflict.")
        newer_exists = any(item.version > manifest.version for item in releases)
        if newer_exists and not same_version:
            raise StudioPublisherError(
                "Studio release version must be newer than the published releases."
            )
        manifest_bytes = manifest.to_json()
        self._put_immutable(
            key=_bundle_key(self._prefix, manifest.version),
            content=content,
            content_type="application/zip",
        )
        if thin_content is not None:
            self._put_immutable(
                key=_thin_bundle_key(self._prefix, manifest.version),
                content=thin_content,
                content_type="application/zip",
            )
        self._put_immutable(
            key=_manifest_key(self._prefix, manifest.version),
            content=manifest_bytes,
            content_type="application/json",
        )
        if newer_exists:
            return
        releases = [item for item in releases if item.version != manifest.version]
        releases.append(manifest)
        releases.sort(key=lambda item: item.version, reverse=True)
        catalog = (
            json.dumps(
                {
                    "releases": [
                        json.loads(item.to_json())
                        for item in releases[:_MAX_STUDIO_RELEASES]
                    ]
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        ).encode()
        self._put_mutable_verified(
            key=_catalog_key(self._prefix),
            content=catalog,
            content_type="application/json",
        )
        self._put_mutable_verified(
            key=_latest_key(self._prefix),
            content=manifest_bytes,
            content_type="application/json",
        )

    def _get_optional_object(self, key: str, max_bytes: int) -> bytes | None:
        try:
            response = self._client.get_object(bucket=self._bucket, key=key)
            return _read_object(response, max_bytes)
        except Exception as error:
            if _is_not_found(error):
                return None
            raise StudioPublisherError(
                "Studio release object lookup failed."
            ) from error

    def _put_immutable(self, *, key: str, content: bytes, content_type: str) -> None:
        existing = self._get_optional_object(key, _MAX_STUDIO_BUNDLE_BYTES)
        if existing is not None:
            if existing != content:
                raise StudioPublisherError("Studio immutable release object conflicts.")
            return
        try:
            self._client.put_object(
                bucket=self._bucket,
                key=key,
                content=content,
                content_type=content_type,
                forbid_overwrite=True,
            )
        except Exception as error:
            existing = self._get_optional_object(key, _MAX_STUDIO_BUNDLE_BYTES)
            if existing == content:
                return
            if existing is not None:
                raise StudioPublisherError(
                    "Studio immutable release object conflicts."
                ) from error
            raise StudioPublisherError(
                "Studio immutable release object upload failed."
            ) from error

    def _put_mutable_verified(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str,
    ) -> None:
        if self._get_optional_object(key, _MAX_STUDIO_BUNDLE_BYTES) == content:
            return
        try:
            self._client.put_object(
                bucket=self._bucket,
                key=key,
                content=content,
                content_type=content_type,
            )
        except Exception as error:
            if self._get_optional_object(key, _MAX_STUDIO_BUNDLE_BYTES) == content:
                return
            raise StudioPublisherError(
                "Studio release pointer upload failed."
            ) from error
        if self._get_optional_object(key, _MAX_STUDIO_BUNDLE_BYTES) != content:
            raise StudioPublisherError("Studio release pointer verification failed.")

    def _existing_releases(self) -> list[StudioReleaseManifest]:
        releases: list[StudioReleaseManifest] = []
        try:
            response = self._client.get_object(
                bucket=self._bucket,
                key=_catalog_key(self._prefix),
            )
            raw_releases = json.loads(_read_object(response, 512 * 1024))["releases"]
            if (
                not isinstance(raw_releases, list)
                or len(raw_releases) > _MAX_STUDIO_RELEASES
            ):
                raise StudioPublisherError("Studio release catalog is invalid.")
            releases = [
                StudioReleaseManifest.from_json(json.dumps(item))
                for item in raw_releases
            ]
        except Exception as error:
            if not _is_not_found(error):
                raise
        try:
            response = self._client.get_object(
                bucket=self._bucket,
                key=_latest_key(self._prefix),
            )
            latest = StudioReleaseManifest.from_json(_read_object(response, 64 * 1024))
        except Exception as error:
            if not _is_not_found(error):
                raise
        else:
            matches = [item for item in releases if item.version == latest.version]
            if matches and matches != [latest]:
                raise StudioPublisherError(
                    "Studio release catalog and latest pointer conflict."
                )
            if not matches:
                releases.append(latest)
        return sorted(releases, key=lambda item: item.version, reverse=True)


class StudioPublicArtifactStore:
    """Publish content-addressed runtime files before a thin release is visible."""

    def __init__(
        self,
        *,
        contract: Any,
        provider: str,
        access_key: str,
        secret_key: str,
        session_token: str,
        client: Any | None = None,
        public_opener: Any | None = None,
    ) -> None:
        if provider not in {"volcengine", "byteplus"}:
            raise StudioPublisherError("Studio artifact provider is invalid.")
        import tos

        self._contract = contract
        self._provider = provider
        self._bucket = contract.STUDIO_ARTIFACT_BUCKETS[provider]
        self._region = contract.STUDIO_ARTIFACT_REGIONS[provider]
        domain = "bytepluses.com" if provider == "byteplus" else "volces.com"
        self._client = client or tos.TosClientV2(
            access_key,
            secret_key,
            security_token=session_token or None,
            endpoint=f"tos-{self._region}.{domain}",
            region=self._region,
        )
        self._public_opener = public_opener or urllib.request.urlopen

    def publish(self, runtime_manifest: Any, artifact_dir: Path) -> tuple[int, int]:
        """Upload missing artifacts, rejecting any immutable-key conflict."""

        if runtime_manifest.provider != self._provider:
            raise StudioPublisherError("Studio artifact provider is invalid.")
        created = 0
        reused = 0
        for artifact in runtime_manifest.artifacts:
            source = artifact_dir / artifact.filename
            if (
                not source.is_file()
                or source.stat().st_size != artifact.size
                or _sha256_file(source) != artifact.sha256
            ):
                raise StudioPublisherError("Studio public artifact is invalid.")
            key = self._contract.studio_artifact_key(
                artifact.sha256,
                artifact.filename,
            )
            head = self._head(key)
            if head is not None:
                self._validate_head(head, artifact)
                self._verify_public(artifact)
                reused += 1
                continue
            try:
                self._client.put_object_from_file(
                    bucket=self._bucket,
                    key=key,
                    file_path=str(source),
                    content_length=artifact.size,
                    content_sha256=artifact.sha256,
                    content_type=_artifact_content_type(artifact.filename),
                    meta={"sha256": artifact.sha256},
                    forbid_overwrite=True,
                )
            except Exception:
                head = self._head(key)
                if head is None:
                    raise StudioPublisherError(
                        "Studio public artifact upload failed."
                    ) from None
                self._validate_head(head, artifact)
                self._verify_public(artifact)
                reused += 1
                continue
            head = self._head(key)
            if head is None:
                raise StudioPublisherError(
                    "Studio public artifact upload could not be verified."
                )
            self._validate_head(head, artifact)
            self._verify_public(artifact)
            created += 1
        return created, reused

    def _head(self, key: str) -> Any | None:
        try:
            return self._client.head_object(bucket=self._bucket, key=key)
        except Exception as error:
            if _is_not_found(error):
                return None
            raise StudioPublisherError(
                "Studio public artifact lookup failed."
            ) from error

    @staticmethod
    def _validate_head(head: Any, artifact: Any) -> None:
        metadata = dict(getattr(head, "meta", None) or {})
        digest = str(metadata.get("sha256", "") or "").lower()
        if (
            int(getattr(head, "content_length", 0) or 0) != artifact.size
            or digest != artifact.sha256
        ):
            raise StudioPublisherError("Studio public artifact key has a conflict.")

    def _verify_public(self, artifact: Any) -> None:
        request = urllib.request.Request(artifact.url, method="HEAD")
        try:
            with self._public_opener(request, timeout=30) as response:
                final_url = str(getattr(response, "geturl", lambda: artifact.url)())
                length = int(response.headers.get("Content-Length", 0) or 0)
                status = int(getattr(response, "status", 200) or 200)
        except Exception as error:
            raise StudioPublisherError(
                "Studio public artifact is not anonymously readable."
            ) from error
        if final_url != artifact.url or status != 200 or length != artifact.size:
            raise StudioPublisherError(
                "Studio public artifact anonymous-read verification failed."
            )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_content_type(filename: str) -> str:
    if filename.endswith(".whl"):
        return "application/zip"
    if filename.endswith(".tar.gz"):
        return "application/gzip"
    return "application/octet-stream"


def _validate_source_checkout(source_root: Path) -> None:
    required = (
        source_root / "pyproject.toml",
        source_root / "uv.lock",
        source_root / "README.md",
        source_root / "LICENSE",
        source_root / "frontend" / "package.json",
        source_root / "frontend" / "package-lock.json",
        source_root / "veadk",
    )
    if not all(path.exists() for path in required):
        raise StudioPublisherError("Release source is not a VeADK checkout.")


def _build_frontend_assets(
    source_root: Path,
    output_dir: Path,
    env: Mapping[str, str],
    *,
    changelog: tuple[str, ...] = (),
) -> None:
    npm = shutil.which("npm", path=env.get("PATH"))
    if npm is None:
        raise StudioPublisherError("npm is required to build the Studio frontend.")
    build_environment = dict(env)
    build_environment["VITE_STUDIO_RELEASE_CHANGELOG"] = json.dumps(
        list(changelog), ensure_ascii=False
    )
    try:
        subprocess.run(
            [npm, "ci"],
            cwd=source_root / "frontend",
            env=build_environment,
            check=True,
        )
        subprocess.run(
            [npm, "run", "build", "--", "--outDir", str(output_dir)],
            cwd=source_root / "frontend",
            env=build_environment,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        raise StudioPublisherError(
            f"Studio frontend build failed with exit code {error.returncode}."
        ) from error
    if not (output_dir / "index.html").is_file():
        raise StudioPublisherError("Studio frontend build produced no index.html.")


def stage_studio_wheel_source(
    source_root: Path,
    frontend_assets: Path,
    wheel_source: Path,
) -> None:
    wheel_source.mkdir(parents=True)
    for filename in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copy2(source_root / filename, wheel_source / filename)
    git_metadata = source_root / ".git"
    if git_metadata.is_file():
        shutil.copy2(git_metadata, wheel_source / ".git")
    elif git_metadata.is_dir():
        (wheel_source / ".git").write_text(
            f"gitdir: {git_metadata.resolve()}\n", encoding="utf-8"
        )
    shutil.copytree(
        source_root / "veadk",
        wheel_source / "veadk",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "webui"),
    )
    frontend_root = source_root / "frontend"

    def ignore_frontend_build_inputs(directory: str, names: list[str]) -> set[str]:
        current = Path(directory)
        ignored = {
            name
            for name in names
            if name == "__pycache__"
            or name.endswith(".pyc")
            or name == ".vite"
            or name == ".env"
            or name.startswith(".env.")
        }
        if current == frontend_root:
            ignored.update(
                {
                    "README.md",
                    "SPEC.md",
                    "dist",
                    "index.html",
                    "node_modules",
                    "package-lock.json",
                    "package.json",
                    "public",
                    "scripts",
                    "skills",
                    "src",
                    "tests",
                    "tsconfig.json",
                    "vite.config.ts",
                    "vite.website-integration.config.ts",
                    "vitest.harness-sidecar.config.ts",
                }.intersection(names)
            )
        return ignored

    shutil.copytree(
        frontend_root,
        wheel_source / "frontend",
        ignore=ignore_frontend_build_inputs,
    )
    shutil.copytree(frontend_assets, wheel_source / "veadk" / "webui")


def studio_runtime_modules(source_root: Path) -> set[str]:
    """List every importable Python module shipped in the Studio wheel."""
    return {
        source.relative_to(source_root).as_posix()
        for package_name in ("veadk", "frontend")
        for source in (source_root / package_name).rglob("*.py")
    }


def validate_studio_wheel(wheel: Path, source_root: Path) -> None:
    """Reject release wheels missing any importable Studio runtime module."""
    required_modules = studio_runtime_modules(source_root)
    try:
        with zipfile.ZipFile(wheel) as archive:
            missing = required_modules.difference(archive.namelist())
    except (OSError, zipfile.BadZipFile) as error:
        raise StudioPublisherError("Built VeADK wheel is invalid.") from error
    if missing:
        raise StudioPublisherError(
            "Built VeADK wheel is missing Studio runtime modules: "
            + ", ".join(sorted(missing))
        )


def validate_studio_agentkit_cli_archive(artifacts: list[Path]) -> Path:
    """Require the exact pinned Linux/x64 native CLI archive."""

    candidates = [path for path in artifacts if path.name == _AGENTKIT_CLI_ARCHIVE]
    if len(candidates) != 1:
        raise StudioPublisherError(
            "The Studio release must contain the pinned AgentKit CLI archive."
        )
    archive = candidates[0]
    try:
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    except OSError as error:
        raise StudioPublisherError(
            "The Studio release AgentKit CLI archive is unavailable."
        ) from error
    if digest != _AGENTKIT_CLI_ARCHIVE_SHA256:
        raise StudioPublisherError(
            "The Studio release AgentKit CLI archive checksum is invalid."
        )
    return archive


def ensure_studio_bundle_agentkit_cli(
    bundle: Path,
    dependency_wheels: Path,
) -> None:
    """Fail closed on a bad CLI and repair a missing archive before publish."""

    try:
        with zipfile.ZipFile(bundle, "r") as archive:
            candidates = [
                name for name in archive.namelist() if name == _AGENTKIT_CLI_ARCHIVE
            ]
            if len(candidates) > 1:
                raise StudioPublisherError(
                    "The Studio release contains duplicate AgentKit CLI archives."
                )
            if candidates:
                digest = hashlib.sha256(archive.read(candidates[0])).hexdigest()
                if digest != _AGENTKIT_CLI_ARCHIVE_SHA256:
                    raise StudioPublisherError(
                        "The Studio release AgentKit CLI archive checksum is invalid."
                    )
                return
    except (OSError, zipfile.BadZipFile) as error:
        raise StudioPublisherError("Built Studio release bundle is invalid.") from error

    cli_archive = validate_studio_agentkit_cli_archive(
        list(dependency_wheels.iterdir())
    )
    try:
        with zipfile.ZipFile(bundle, "a") as archive:
            archive.write(
                cli_archive,
                _AGENTKIT_CLI_ARCHIVE,
                compress_type=zipfile.ZIP_STORED,
            )
    except (OSError, zipfile.BadZipFile) as error:
        raise StudioPublisherError(
            "Could not add the AgentKit CLI archive to the Studio release."
        ) from error

    with zipfile.ZipFile(bundle, "r") as archive:
        digest = hashlib.sha256(archive.read(_AGENTKIT_CLI_ARCHIVE)).hexdigest()
    if digest != _AGENTKIT_CLI_ARCHIVE_SHA256:
        raise StudioPublisherError(
            "The Studio release AgentKit CLI archive checksum is invalid."
        )


def validate_studio_bundle_dependencies(package_dir: Path) -> Path:
    """Validate the local VeADK/CLI dependency pair in an extracted bundle."""
    requirements_path = package_dir / "requirements.txt"
    try:
        lines = requirements_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise StudioPublisherError(
            "Studio release requirements are unavailable."
        ) from error
    runtime_manifest_path = package_dir / _STUDIO_RUNTIME_MANIFEST
    if runtime_manifest_path.is_file():
        try:
            from veadk.cli.studio_artifacts import StudioRuntimeManifest

            runtime_manifest = StudioRuntimeManifest.from_json(
                runtime_manifest_path.read_bytes()
            )
        except (ImportError, OSError, ValueError) as error:
            raise StudioPublisherError("Studio runtime manifest is invalid.") from error
        cli_artifact = runtime_manifest.agentkit_cli()
        remote_veadk_wheels = [
            item
            for item in runtime_manifest.artifacts
            if item.kind == "wheel"
            and item.filename.startswith(("veadk_python-", "veadk-python-"))
        ]
        local_veadk_wheels = sorted(package_dir.glob("veadk*.whl"))
        expected_requirements = runtime_manifest.remote_requirements()
        if len(local_veadk_wheels) == 1:
            local_veadk = local_veadk_wheels[0]
            expected_requirements += (
                f"./{local_veadk.name} --hash=sha256:{_sha256_file(local_veadk)}\n"
            )
        bundled_wheelhouse = package_dir / "bundled-wheelhouse"
        bundled_files = (
            sorted(path for path in bundled_wheelhouse.iterdir() if path.is_file())
            if bundled_wheelhouse.is_dir()
            else []
        )
        bundled_valid = len(bundled_files) == len(runtime_manifest.bundled_artifacts)
        if bundled_valid:
            expected_bundled = {
                item.filename: item for item in runtime_manifest.bundled_artifacts
            }
            bundled_valid = all(
                path.name in expected_bundled
                and path.stat().st_size == expected_bundled[path.name].size
                and _sha256_file(path) == expected_bundled[path.name].sha256
                for path in bundled_files
            )
        if (
            cli_artifact.filename != _AGENTKIT_CLI_ARCHIVE
            or cli_artifact.sha256 != _AGENTKIT_CLI_ARCHIVE_SHA256
            or remote_veadk_wheels
            or len(local_veadk_wheels) != 1
            or requirements_path.read_text(encoding="utf-8") != expected_requirements
            or (package_dir / "wheelhouse").exists()
            or (package_dir / _AGENTKIT_CLI_ARCHIVE).exists()
            or not bundled_valid
        ):
            raise StudioPublisherError(
                "Studio thin release dependency contract is invalid."
            )
        return runtime_manifest_path
    local_wheels: list[Path] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            tokens = shlex.split(line)
        except ValueError as error:
            raise StudioPublisherError(
                "Studio release requirements contain invalid quoting."
            ) from error
        if not tokens or not tokens[0].endswith(".whl"):
            continue
        relative = tokens[0].removeprefix("./")
        path = (package_dir / relative).resolve()
        if not path.is_relative_to(package_dir.resolve()) or not path.is_file():
            raise StudioPublisherError(
                "Studio release requirements reference a missing local wheel."
            )
        local_wheels.append(path)
    veadk_wheels = [
        wheel
        for wheel in local_wheels
        if wheel.name.startswith(("veadk_python-", "veadk-python-"))
    ]
    if len(veadk_wheels) != 1:
        raise StudioPublisherError(
            "The Studio release must contain exactly one local VeADK wheel."
        )
    return validate_studio_agentkit_cli_archive(list(package_dir.iterdir()))


def _build_local_requirements(
    source_root: Path,
    package_dir: Path,
    frontend_assets: Path,
    dependency_wheels: Path,
    env: Mapping[str, str],
) -> str:
    wheel_source = package_dir / "wheel-source"
    stage_studio_wheel_source(source_root, frontend_assets, wheel_source)
    uv = shutil.which("uv", path=env.get("PATH"))
    if uv is None:
        raise StudioPublisherError("uv is required to build the VeADK wheel.")
    try:
        subprocess.run(
            [uv, "build", "--wheel", str(wheel_source), "-o", str(package_dir)],
            env=env,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        raise StudioPublisherError(
            f"Local VeADK wheel build failed with exit code {error.returncode}."
        ) from error
    built_wheels = sorted(package_dir.glob("veadk*.whl"))
    if len(built_wheels) != 1:
        raise StudioPublisherError(
            "Local source build did not produce one VeADK wheel."
        )
    validate_studio_wheel(built_wheels[0], wheel_source)
    archive_source = dependency_wheels / _AGENTKIT_CLI_ARCHIVE
    if archive_source.is_file():
        shutil.copy2(archive_source, package_dir / archive_source.name)
    validate_studio_agentkit_cli_archive(list(package_dir.iterdir()))
    shutil.rmtree(wheel_source)
    dependency_sources = sorted(
        path
        for path in dependency_wheels.glob("*.tar.gz")
        if path.name != _AGENTKIT_CLI_ARCHIVE
    )
    try:
        return build_studio_offline_runtime(
            source_root,
            package_dir,
            veadk_wheel=built_wheels[0],
            dependency_sources=dependency_sources,
            environment=env,
        )
    except ValueError as error:
        raise StudioPublisherError(str(error)) from error


def _studio_run_script(*, thin: bool = False) -> str:
    companion = (
        "python3 -m veadk.cli.studio_companion "
        f'--runtime-manifest "$ROOT_DIR/{_STUDIO_RUNTIME_MANIFEST}" '
        '--provider "${CLOUD_PROVIDER:-${AGENTKIT_CLOUD_PROVIDER:-volcengine}}"\n'
        if thin
        else "python3 -m veadk.cli.studio_companion "
        f'--archive "$ROOT_DIR/{_AGENTKIT_CLI_ARCHIVE}"\n'
    )
    return (
        "#!/bin/bash\n"
        "set -ex\n"
        'ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"\n'
        'cd "$ROOT_DIR"\n'
        'if [ -d "output" ]; then cd ./output/; fi\n'
        "HOST=0.0.0.0\n"
        "PORT=${_FAAS_RUNTIME_PORT:-8000}\n"
        'export PYTHONPATH="./site-packages${PYTHONPATH:+:$PYTHONPATH}"\n'
        f"{companion}"
        "exec python3 -m veadk.cli.cli studio "
        '--provider "${CLOUD_PROVIDER:-${AGENTKIT_CLOUD_PROVIDER:-volcengine}}" '
        "--auth-mode frontend "
        '--host "$HOST" --port "$PORT"\n'
    )


def _load_studio_artifact_contract(source_root: Path) -> Any:
    contract_path = source_root / "veadk" / "cli" / "studio_artifacts.py"
    if not contract_path.is_file():
        raise StudioPublisherError("Studio artifact contract is missing.")
    module_name = "veadk_studio_artifact_contract"
    spec = importlib.util.spec_from_file_location(module_name, contract_path)
    if spec is None or spec.loader is None:
        raise StudioPublisherError("Studio artifact contract is unavailable.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as error:
        raise StudioPublisherError("Studio artifact contract is invalid.") from error
    return module


def stage_studio_thin_runtime(
    source_root: Path,
    package_dir: Path,
    output_dir: Path,
    *,
    provider: str,
) -> tuple[str, Path]:
    """Replace local runtime payloads with one exact public artifact manifest."""

    contract = _load_studio_artifact_contract(source_root)
    wheelhouse = package_dir / "wheelhouse"
    wheels = sorted(wheelhouse.glob("*.whl"))
    runtime_veadk_wheels = [
        path
        for path in wheels
        if path.name.startswith(("veadk_python-", "veadk-python-"))
    ]
    dependency_wheels = [path for path in wheels if path not in runtime_veadk_wheels]
    local_veadk_wheels = sorted(package_dir.glob("veadk*.whl"))
    if len(runtime_veadk_wheels) == 1 and not local_veadk_wheels:
        local_veadk = package_dir / runtime_veadk_wheels[0].name
        shutil.copy2(runtime_veadk_wheels[0], local_veadk)
        local_veadk_wheels = [local_veadk]
    cli_archive = package_dir / _AGENTKIT_CLI_ARCHIVE
    if (
        not dependency_wheels
        or len(runtime_veadk_wheels) != 1
        or len(local_veadk_wheels) != 1
        or _sha256_file(runtime_veadk_wheels[0]) != _sha256_file(local_veadk_wheels[0])
        or not cli_archive.is_file()
    ):
        raise StudioPublisherError("Studio offline runtime is incomplete.")
    validate_studio_agentkit_cli_archive([cli_archive])
    public_wheels, bundled_wheels = partition_public_runtime_wheels(
        source_root,
        dependency_wheels,
    )
    artifacts = tuple(
        contract.StudioArtifact.from_path(
            path,
            provider=provider,
            kind="wheel",
        )
        for path in public_wheels
    ) + (
        contract.StudioArtifact.from_path(
            cli_archive,
            provider=provider,
            kind="agentkit-cli",
        ),
    )
    bundled_artifacts = tuple(
        contract.StudioBundledArtifact.from_path(path) for path in bundled_wheels
    )
    runtime_manifest = contract.StudioRuntimeManifest.create(
        provider,
        artifacts,
        bundled_artifacts,
    )
    artifact_dir = output_dir / f"runtime-artifacts-{runtime_manifest.runtime_epoch}"
    artifact_dir.mkdir(parents=True, exist_ok=False)
    for path in (*public_wheels, cli_archive):
        shutil.copy2(path, artifact_dir / path.name)
    if bundled_wheels:
        bundled_wheelhouse = package_dir / "bundled-wheelhouse"
        bundled_wheelhouse.mkdir()
        for path in bundled_wheels:
            shutil.copy2(path, bundled_wheelhouse / path.name)
    manifest_content = runtime_manifest.to_json()
    (package_dir / _STUDIO_RUNTIME_MANIFEST).write_bytes(manifest_content)
    (
        output_dir / f"runtime-manifest-{runtime_manifest.runtime_epoch}.json"
    ).write_bytes(manifest_content)
    (package_dir / "requirements.txt").write_text(
        runtime_manifest.remote_requirements()
        + f"./{local_veadk_wheels[0].name} "
        + f"--hash=sha256:{_sha256_file(local_veadk_wheels[0])}\n",
        encoding="utf-8",
    )
    shutil.rmtree(wheelhouse)
    cli_archive.unlink()
    (package_dir / "run.sh").write_text(
        _studio_run_script(thin=True),
        encoding="utf-8",
        newline="\n",
    )
    return runtime_manifest.runtime_epoch, artifact_dir


def partition_public_runtime_wheels(
    source_root: Path,
    wheels: list[Path],
) -> tuple[list[Path], list[Path]]:
    """Keep non-approved wheels private instead of weakening the public gate."""

    public: list[Path] = []
    bundled: list[Path] = []
    for wheel in wheels:
        try:
            validate_public_runtime_provenance(source_root, [wheel])
        except StudioPublisherError as error:
            if not any(
                marker in str(error)
                for marker in (
                    "non-PyPI wheel",
                    "has no locked wheel",
                    "license is not allowlisted",
                )
            ):
                raise
            bundled.append(wheel)
        else:
            public.append(wheel)
    return public, bundled


def validate_public_runtime_provenance(
    source_root: Path,
    wheels: list[Path],
) -> None:
    """Allow public publication only for the local project and PyPI lock entries."""

    from packaging.utils import canonicalize_name, parse_wheel_filename

    lock_path = source_root / "uv.lock"
    try:
        lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
        packages = lock["package"]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as error:
        raise StudioPublisherError(
            "Studio public artifact provenance is invalid."
        ) from error
    allowed: dict[str, set[tuple[str, int, str]]] = {
        canonicalize_name("veadk-python"): set()
    }
    for package in packages:
        if not isinstance(package, dict):
            raise StudioPublisherError("Studio public artifact provenance is invalid.")
        name = package.get("name")
        source = package.get("source")
        if not isinstance(name, str) or not isinstance(source, dict):
            raise StudioPublisherError("Studio public artifact provenance is invalid.")
        if source.get("registry") == "https://pypi.org/simple":
            identities = allowed.setdefault(canonicalize_name(name), set())
            locked_wheels = package.get("wheels", [])
            if not isinstance(locked_wheels, list):
                raise StudioPublisherError(
                    "Studio public artifact provenance is invalid."
                )
            for wheel in locked_wheels:
                if not isinstance(wheel, dict):
                    raise StudioPublisherError(
                        "Studio public artifact provenance is invalid."
                    )
                url = wheel.get("url")
                digest = wheel.get("hash")
                size = wheel.get("size")
                if (
                    not isinstance(url, str)
                    or not isinstance(digest, str)
                    or not isinstance(size, int)
                    or size <= 0
                    or not digest.startswith("sha256:")
                    or not _SHA256_PATTERN.fullmatch(digest.removeprefix("sha256:"))
                ):
                    raise StudioPublisherError(
                        "Studio public artifact provenance is invalid."
                    )
                parsed = urllib.parse.urlsplit(url)
                filename = urllib.parse.unquote(Path(parsed.path).name)
                if (
                    parsed.scheme != "https"
                    or parsed.hostname != "files.pythonhosted.org"
                    or parsed.port is not None
                    or parsed.username is not None
                    or parsed.password is not None
                    or parsed.query
                    or parsed.fragment
                ):
                    raise StudioPublisherError(
                        "Studio public artifact provenance is invalid."
                    )
                identities.add((filename, size, digest.removeprefix("sha256:")))
    try:
        published = {path: parse_wheel_filename(path.name)[0] for path in wheels}
    except ValueError as error:
        raise StudioPublisherError(
            "Studio public artifact wheel is invalid."
        ) from error
    disallowed = sorted(str(name) for name in published.values() if name not in allowed)
    if disallowed:
        raise StudioPublisherError(
            "Studio public runtime contains a non-PyPI wheel: " + ", ".join(disallowed)
        )
    for path, name in published.items():
        identity = (path.name, path.stat().st_size, _sha256_file(path))
        if not allowed[name]:
            raise StudioPublisherError(
                f"Studio public runtime package has no locked wheel: {name}"
            )
        if identity not in allowed[name]:
            raise StudioPublisherError(
                f"Studio public runtime wheel does not match uv.lock: {name}"
            )
    license_rejections: list[str] = []
    for path, name in published.items():
        try:
            _validate_public_wheel_license(path, str(name))
        except StudioPublisherError as error:
            if "license is not allowlisted" not in str(error):
                raise
            license_rejections.append(str(name))
    if license_rejections:
        raise StudioPublisherError(
            "Studio public runtime wheel license is not allowlisted: "
            + ", ".join(sorted(license_rejections))
        )


def _validate_public_wheel_license(path: Path, expected_name: str) -> None:
    """Require one explicit, allowlisted redistributable wheel license."""

    from packaging.licenses import (
        InvalidLicenseExpression,
        canonicalize_license_expression,
    )
    from packaging.utils import canonicalize_name

    try:
        with zipfile.ZipFile(path) as archive:
            metadata_names = [
                name
                for name in archive.namelist()
                if name.count("/") == 1 and name.endswith(".dist-info/METADATA")
            ]
            if len(metadata_names) != 1:
                raise StudioPublisherError(
                    "Studio public runtime wheel metadata is invalid."
                )
            metadata = BytesParser(policy=cast(Any, email_policy)).parsebytes(
                archive.read(metadata_names[0])
            )
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise StudioPublisherError(
            "Studio public runtime wheel metadata is invalid."
        ) from error
    if canonicalize_name(str(metadata.get("Name", ""))) != canonicalize_name(
        expected_name
    ):
        raise StudioPublisherError("Studio public runtime wheel metadata is invalid.")

    expression = str(metadata.get("License-Expression", "") or "").strip()
    if not expression:
        classifiers = [
            value.strip()
            for value in metadata.get_all("Classifier", [])
            if value.strip().startswith("License ::")
        ]
        mapped = {
            _PUBLIC_RUNTIME_LICENSE_CLASSIFIERS[value]
            for value in classifiers
            if value in _PUBLIC_RUNTIME_LICENSE_CLASSIFIERS
        }
        unknown_classifiers = {
            value
            for value in classifiers
            if value not in _PUBLIC_RUNTIME_LICENSE_CLASSIFIERS
            and value != "License :: OSI Approved"
        }
        if mapped and not unknown_classifiers:
            expression = " OR ".join(sorted(mapped))
        elif not classifiers:
            raw_legacy = str(metadata.get("License", "") or "").strip()
            if raw_legacy and len(raw_legacy) <= 200:
                try:
                    expression = canonicalize_license_expression(raw_legacy)
                except InvalidLicenseExpression:
                    expression = ""
            legacy = re.sub(
                r"[^a-z0-9]+",
                " ",
                raw_legacy.lower(),
            ).strip()
            expression = expression or _PUBLIC_RUNTIME_LEGACY_LICENSES.get(
                legacy,
                "",
            )
            if not expression and legacy.startswith("apache license version 2 0"):
                expression = "Apache-2.0"
            if not expression and legacy.startswith("mit license copyright"):
                expression = "MIT"
    try:
        normalized = canonicalize_license_expression(expression)
    except InvalidLicenseExpression as error:
        raise StudioPublisherError(
            "Studio public runtime wheel license is not allowlisted."
        ) from error
    tokens = {
        token
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9.+-]*", normalized)
        if token not in {"AND", "OR", "WITH"}
    }
    if not tokens or not tokens.issubset(_PUBLIC_RUNTIME_LICENSES):
        raise StudioPublisherError(
            "Studio public runtime wheel license is not allowlisted."
        )


def _zip_directory(source: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source))


def build_studio_release(
    *,
    source_root: Path,
    output_dir: Path,
    version: str,
    git_sha: str,
    changelog: tuple[str, ...],
    frontend_assets: Path | None,
    dependency_wheels: Path,
    env: Mapping[str, str],
    thin: bool = False,
    provider: str = "volcengine",
) -> tuple[Path, StudioReleaseManifest]:
    """Build a release while treating VeADK only as source input."""
    _validate_source_checkout(source_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="studio_release_publisher_") as tmp:
        workspace = Path(tmp)
        resolved_frontend = frontend_assets
        if resolved_frontend is None:
            resolved_frontend = workspace / "frontend"
            _build_frontend_assets(
                source_root,
                resolved_frontend,
                env,
                changelog=changelog,
            )
        elif not (resolved_frontend / "index.html").is_file():
            raise StudioPublisherError(
                "Prepared Studio frontend assets contain no index.html."
            )
        package_dir = workspace / "package"
        package_dir.mkdir()
        requirements = _build_local_requirements(
            source_root,
            package_dir,
            resolved_frontend,
            dependency_wheels,
            env,
        )
        (package_dir / "run.sh").write_text(
            _studio_run_script(),
            encoding="utf-8",
            newline="\n",
        )
        (package_dir / "requirements.txt").write_text(requirements, encoding="utf-8")
        runtime_epoch = ""
        bundle = output_dir / f"studio-bundle-{version}.zip"
        _zip_directory(package_dir, bundle)
        thin_bundle: Path | None = None
        if thin:
            runtime_epoch, _artifact_dir = stage_studio_thin_runtime(
                source_root,
                package_dir,
                output_dir,
                provider=provider,
            )
            thin_bundle = output_dir / f"studio-bundle-{version}-thin.zip"
            _zip_directory(package_dir, thin_bundle)
    ensure_studio_bundle_agentkit_cli(bundle, dependency_wheels)
    content = bundle.read_bytes()
    thin_content = thin_bundle.read_bytes() if thin_bundle is not None else b""
    manifest = StudioReleaseManifest(
        version=version,
        git_sha=git_sha,
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
        created_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(
            timespec="seconds"
        ),
        changelog=changelog,
        runtime_epoch=runtime_epoch,
        thin_sha256=(hashlib.sha256(thin_content).hexdigest() if thin_content else ""),
        thin_size=len(thin_content),
    )
    (output_dir / f"manifest-{version}.json").write_bytes(manifest.to_json())
    return bundle, manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument(
        "--provider",
        choices=("volcengine", "byteplus"),
        default="volcengine",
    )
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--changelog", action="append", default=[])
    parser.add_argument("--frontend-assets", type=Path)
    parser.add_argument("--dependency-wheels", type=Path, required=True)
    parser.add_argument("--thin", action="store_true")
    parser.add_argument(
        "--release-contract",
        choices=(_STUDIO_RELEASE_CONTRACT,),
        required=True,
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    bundle, manifest = build_studio_release(
        source_root=args.source_root.resolve(),
        output_dir=args.output_dir.resolve(),
        version=args.version,
        git_sha=args.git_sha,
        changelog=tuple(args.changelog),
        frontend_assets=args.frontend_assets,
        dependency_wheels=args.dependency_wheels,
        env=os.environ,
        thin=args.thin,
        provider=args.provider,
    )
    credential_prefix = "BYTEPLUS" if args.provider == "byteplus" else "VOLCENGINE"
    access_key = os.getenv(f"{credential_prefix}_ACCESS_KEY", "")
    secret_key = os.getenv(f"{credential_prefix}_SECRET_KEY", "")
    session_token = os.getenv(f"{credential_prefix}_SESSION_TOKEN", "")
    artifact_counts = (0, 0)
    if args.thin:
        contract = _load_studio_artifact_contract(args.source_root.resolve())
        runtime_manifest = contract.StudioRuntimeManifest.from_json(
            (
                args.output_dir.resolve()
                / f"runtime-manifest-{manifest.runtime_epoch}.json"
            ).read_bytes()
        )
        artifact_counts = StudioPublicArtifactStore(
            contract=contract,
            provider=args.provider,
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
        ).publish(
            runtime_manifest,
            args.output_dir.resolve() / f"runtime-artifacts-{manifest.runtime_epoch}",
        )
    store = StudioReleaseStore(
        bucket=args.bucket,
        region=args.region,
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        prefix=args.prefix,
        provider=args.provider,
    )
    store.publish(
        bundle,
        manifest,
        thin_bundle=(
            args.output_dir.resolve() / f"studio-bundle-{manifest.version}-thin.zip"
            if args.thin
            else None
        ),
    )
    print(
        json.dumps(
            {
                "version": manifest.version,
                "gitSha": manifest.git_sha,
                "sha256": manifest.sha256,
                "size": manifest.size,
                "runtimeEpoch": manifest.runtime_epoch,
                "thinSha256": manifest.thin_sha256,
                "thinSize": manifest.thin_size,
                "artifactsCreated": artifact_counts[0],
                "artifactsReused": artifact_counts[1],
            }
        )
    )


if __name__ == "__main__":
    main()
