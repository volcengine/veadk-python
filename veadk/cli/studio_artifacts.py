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

"""Immutable public artifacts used by thin Studio release bundles."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from typing import Literal, TypeAlias

CloudProvider: TypeAlias = Literal["volcengine", "byteplus"]

STUDIO_ARTIFACT_SCHEMA_VERSION = 2
STUDIO_ARTIFACT_PREFIX = "veadk/studio/artifacts/v1"
STUDIO_BUNDLED_WHEELHOUSE = "bundled-wheelhouse"
STUDIO_RUNTIME_PLATFORM = "linux-x64"
STUDIO_RUNTIME_PYTHON_ABI = "cp312"
STUDIO_ARTIFACT_BUCKETS: dict[CloudProvider, str] = {
    "volcengine": "veadk-studio-public",
    "byteplus": "veadk-studio-byteplus-public",
}
STUDIO_ARTIFACT_REGIONS: dict[CloudProvider, str] = {
    "volcengine": "cn-beijing",
    "byteplus": "ap-southeast-1",
}

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,254}$")
_MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
_MAX_RUNTIME_BYTES = 2 * 1024 * 1024 * 1024
_DOWNLOAD_CHUNK_BYTES = 1024 * 1024


def studio_artifact_host(provider: CloudProvider) -> str:
    """Return the provider-local anonymous-read artifact host."""

    bucket = STUDIO_ARTIFACT_BUCKETS[provider]
    region = STUDIO_ARTIFACT_REGIONS[provider]
    domain = "bytepluses.com" if provider == "byteplus" else "volces.com"
    return f"{bucket}.tos-{region}.{domain}"


def studio_artifact_base_url(provider: CloudProvider) -> str:
    """Return the immutable public artifact prefix for one provider."""

    return f"https://{studio_artifact_host(provider)}/{STUDIO_ARTIFACT_PREFIX}"


def studio_artifact_key(sha256: str, filename: str) -> str:
    """Return the content-addressed object key for one artifact."""

    _validate_sha256(sha256)
    _validate_filename(filename)
    return f"{STUDIO_ARTIFACT_PREFIX}/{sha256}/{filename}"


def studio_artifact_url(
    provider: CloudProvider,
    sha256: str,
    filename: str,
) -> str:
    """Return a provider-local immutable public URL."""

    return f"https://{studio_artifact_host(provider)}/{studio_artifact_key(sha256, filename)}"


@dataclass(frozen=True)
class StudioArtifact:
    """One immutable file required by a Studio runtime epoch."""

    provider: CloudProvider
    kind: str
    platform: str
    python_abi: str
    filename: str
    url: str
    size: int
    sha256: str

    def __post_init__(self) -> None:
        if self.provider not in {"volcengine", "byteplus"}:
            raise ValueError("Studio artifact provider is invalid.")
        if self.kind not in {"wheel", "agentkit-cli"}:
            raise ValueError("Studio artifact kind is invalid.")
        if self.platform != STUDIO_RUNTIME_PLATFORM:
            raise ValueError("Studio artifact platform is invalid.")
        if self.python_abi != STUDIO_RUNTIME_PYTHON_ABI:
            raise ValueError("Studio artifact Python ABI is invalid.")
        _validate_filename(self.filename)
        _validate_sha256(self.sha256)
        if self.size <= 0 or self.size > _MAX_ARTIFACT_BYTES:
            raise ValueError("Studio artifact size is invalid.")
        _validate_artifact_url(self.url, self.provider, self.sha256, self.filename)

    @classmethod
    def from_path(
        cls,
        path: Path,
        *,
        provider: CloudProvider,
        kind: str = "wheel",
    ) -> StudioArtifact:
        """Create exact metadata from an already-built local artifact."""

        digest = _sha256(path)
        return cls(
            provider=provider,
            kind=kind,
            platform=STUDIO_RUNTIME_PLATFORM,
            python_abi=STUDIO_RUNTIME_PYTHON_ABI,
            filename=path.name,
            url=studio_artifact_url(provider, digest, path.name),
            size=path.stat().st_size,
            sha256=digest,
        )

    def to_dict(self) -> dict[str, object]:
        """Serialize using stable public field names."""

        return {
            "provider": self.provider,
            "kind": self.kind,
            "platform": self.platform,
            "pythonAbi": self.python_abi,
            "filename": self.filename,
            "url": self.url,
            "size": self.size,
            "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, payload: object) -> StudioArtifact:
        """Parse fail-closed artifact metadata."""

        if not isinstance(payload, dict) or set(payload) != {
            "provider",
            "kind",
            "platform",
            "pythonAbi",
            "filename",
            "url",
            "size",
            "sha256",
        }:
            raise ValueError("Studio artifact metadata is invalid.")
        if (
            not all(
                isinstance(payload[field], str)
                for field in (
                    "provider",
                    "kind",
                    "platform",
                    "pythonAbi",
                    "filename",
                    "url",
                    "sha256",
                )
            )
            or not isinstance(payload["size"], int)
            or isinstance(payload["size"], bool)
        ):
            raise ValueError("Studio artifact metadata is invalid.")
        try:
            return cls(
                provider=payload["provider"],  # type: ignore[arg-type]
                kind=payload["kind"],
                platform=payload["platform"],
                python_abi=payload["pythonAbi"],
                filename=payload["filename"],
                url=payload["url"],
                size=payload["size"],
                sha256=payload["sha256"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Studio artifact metadata is invalid.") from error


@dataclass(frozen=True)
class StudioBundledArtifact:
    """One exact dependency retained in the private Studio release bundle."""

    kind: str
    platform: str
    python_abi: str
    filename: str
    size: int
    sha256: str

    def __post_init__(self) -> None:
        if self.kind != "wheel" or not self.filename.endswith(".whl"):
            raise ValueError("Studio bundled artifact kind is invalid.")
        if self.platform != STUDIO_RUNTIME_PLATFORM:
            raise ValueError("Studio bundled artifact platform is invalid.")
        if self.python_abi != STUDIO_RUNTIME_PYTHON_ABI:
            raise ValueError("Studio bundled artifact Python ABI is invalid.")
        _validate_filename(self.filename)
        _validate_sha256(self.sha256)
        if self.size <= 0 or self.size > _MAX_ARTIFACT_BYTES:
            raise ValueError("Studio bundled artifact size is invalid.")

    @classmethod
    def from_path(cls, path: Path) -> StudioBundledArtifact:
        return cls(
            kind="wheel",
            platform=STUDIO_RUNTIME_PLATFORM,
            python_abi=STUDIO_RUNTIME_PYTHON_ABI,
            filename=path.name,
            size=path.stat().st_size,
            sha256=_sha256(path),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "platform": self.platform,
            "pythonAbi": self.python_abi,
            "filename": self.filename,
            "size": self.size,
            "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, payload: object) -> StudioBundledArtifact:
        if not isinstance(payload, dict) or set(payload) != {
            "kind",
            "platform",
            "pythonAbi",
            "filename",
            "size",
            "sha256",
        }:
            raise ValueError("Studio bundled artifact metadata is invalid.")
        if (
            not all(
                isinstance(payload[field], str)
                for field in (
                    "kind",
                    "platform",
                    "pythonAbi",
                    "filename",
                    "sha256",
                )
            )
            or not isinstance(payload["size"], int)
            or isinstance(payload["size"], bool)
        ):
            raise ValueError("Studio bundled artifact metadata is invalid.")
        try:
            return cls(
                kind=payload["kind"],
                platform=payload["platform"],
                python_abi=payload["pythonAbi"],
                filename=payload["filename"],
                size=payload["size"],
                sha256=payload["sha256"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Studio bundled artifact metadata is invalid.") from error


@dataclass(frozen=True)
class StudioRuntimeManifest:
    """The exact public dependency set reused by ordinary Studio releases."""

    provider: CloudProvider
    runtime_epoch: str
    artifacts: tuple[StudioArtifact, ...]
    bundled_artifacts: tuple[StudioBundledArtifact, ...] = ()
    schema_version: int = STUDIO_ARTIFACT_SCHEMA_VERSION
    platform: str = STUDIO_RUNTIME_PLATFORM
    python_abi: str = STUDIO_RUNTIME_PYTHON_ABI

    def __post_init__(self) -> None:
        if self.schema_version != STUDIO_ARTIFACT_SCHEMA_VERSION:
            raise ValueError("Studio runtime manifest schema is unsupported.")
        if self.provider not in {"volcengine", "byteplus"}:
            raise ValueError("Studio runtime manifest provider is invalid.")
        if self.platform != STUDIO_RUNTIME_PLATFORM:
            raise ValueError("Studio runtime manifest platform is invalid.")
        if self.python_abi != STUDIO_RUNTIME_PYTHON_ABI:
            raise ValueError("Studio runtime manifest Python ABI is invalid.")
        _validate_sha256(self.runtime_epoch)
        if (
            not self.artifacts
            or len(self.artifacts) + len(self.bundled_artifacts) > 512
            or sum(item.size for item in (*self.artifacts, *self.bundled_artifacts))
            > _MAX_RUNTIME_BYTES
        ):
            raise ValueError("Studio runtime manifest artifact count is invalid.")
        filenames: set[str] = set()
        wheel_count = 0
        cli_count = 0
        for artifact in self.artifacts:
            if (
                artifact.provider != self.provider
                or artifact.platform != self.platform
                or artifact.python_abi != self.python_abi
                or artifact.filename in filenames
            ):
                raise ValueError("Studio runtime manifest artifact is invalid.")
            filenames.add(artifact.filename)
            if artifact.kind == "wheel":
                if not artifact.filename.endswith(".whl"):
                    raise ValueError("Studio runtime manifest wheel is invalid.")
                wheel_count += 1
            elif artifact.kind == "agentkit-cli":
                cli_count += 1
        for artifact in self.bundled_artifacts:
            if (
                artifact.platform != self.platform
                or artifact.python_abi != self.python_abi
                or artifact.filename in filenames
            ):
                raise ValueError("Studio bundled runtime artifact is invalid.")
            filenames.add(artifact.filename)
            wheel_count += 1
        if wheel_count == 0 or cli_count != 1:
            raise ValueError("Studio runtime manifest artifact set is incomplete.")
        if self.runtime_epoch != runtime_epoch(
            self.artifacts,
            self.bundled_artifacts,
        ):
            raise ValueError("Studio runtime manifest epoch is invalid.")

    @classmethod
    def create(
        cls,
        provider: CloudProvider,
        artifacts: tuple[StudioArtifact, ...],
        bundled_artifacts: tuple[StudioBundledArtifact, ...] = (),
    ) -> StudioRuntimeManifest:
        """Create a stable epoch from exact artifact bytes."""

        return cls(
            provider=provider,
            runtime_epoch=runtime_epoch(artifacts, bundled_artifacts),
            artifacts=artifacts,
            bundled_artifacts=bundled_artifacts,
        )

    def to_json(self) -> bytes:
        """Serialize deterministically for bundle signing and review."""

        payload = {
            "schemaVersion": self.schema_version,
            "provider": self.provider,
            "platform": self.platform,
            "pythonAbi": self.python_abi,
            "runtimeEpoch": self.runtime_epoch,
            "artifacts": [item.to_dict() for item in self.artifacts],
            "bundledArtifacts": [item.to_dict() for item in self.bundled_artifacts],
        }
        return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()

    def remote_requirements(self) -> str:
        """Return a deterministic pip input containing only pinned public wheels."""

        wheels = sorted(
            (item for item in self.artifacts if item.kind == "wheel"),
            key=lambda item: item.filename,
        )
        return (
            "--no-index\n"
            + "".join(f"{item.url}#sha256={item.sha256}\n" for item in wheels)
            + "".join(
                f"./{STUDIO_BUNDLED_WHEELHOUSE}/{item.filename} "
                f"--hash=sha256:{item.sha256}\n"
                for item in sorted(
                    self.bundled_artifacts,
                    key=lambda value: value.filename,
                )
            )
        )

    def agentkit_cli(self) -> StudioArtifact:
        """Return the manifest's unique pinned AgentKit CLI artifact."""

        return next(item for item in self.artifacts if item.kind == "agentkit-cli")

    @classmethod
    def from_json(cls, content: bytes | str) -> StudioRuntimeManifest:
        """Parse a bounded, exact manifest without accepting extra fields."""

        if isinstance(content, bytes):
            if len(content) > 1024 * 1024:
                raise ValueError("Studio runtime manifest is too large.")
            text = content.decode("utf-8")
        else:
            text = content
            if len(text.encode()) > 1024 * 1024:
                raise ValueError("Studio runtime manifest is too large.")
        try:
            payload = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Studio runtime manifest is invalid.") from error
        if not isinstance(payload, dict) or set(payload) != {
            "schemaVersion",
            "provider",
            "platform",
            "pythonAbi",
            "runtimeEpoch",
            "artifacts",
            "bundledArtifacts",
        }:
            raise ValueError("Studio runtime manifest is invalid.")
        raw_artifacts = payload.get("artifacts")
        raw_bundled_artifacts = payload.get("bundledArtifacts")
        if not isinstance(raw_artifacts, list) or not isinstance(
            raw_bundled_artifacts,
            list,
        ):
            raise ValueError("Studio runtime manifest is invalid.")
        if (
            not isinstance(payload["schemaVersion"], int)
            or isinstance(payload["schemaVersion"], bool)
            or not all(
                isinstance(payload[field], str)
                for field in (
                    "provider",
                    "platform",
                    "pythonAbi",
                    "runtimeEpoch",
                )
            )
        ):
            raise ValueError("Studio runtime manifest is invalid.")
        try:
            return cls(
                schema_version=payload["schemaVersion"],
                provider=payload["provider"],  # type: ignore[arg-type]
                platform=payload["platform"],
                python_abi=payload["pythonAbi"],
                runtime_epoch=payload["runtimeEpoch"],
                artifacts=tuple(
                    StudioArtifact.from_dict(item) for item in raw_artifacts
                ),
                bundled_artifacts=tuple(
                    StudioBundledArtifact.from_dict(item)
                    for item in raw_bundled_artifacts
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Studio runtime manifest is invalid.") from error


def runtime_epoch(
    artifacts: tuple[StudioArtifact, ...],
    bundled_artifacts: tuple[StudioBundledArtifact, ...] = (),
) -> str:
    """Hash content identity while remaining independent of provider host."""

    payload = [
        {
            "kind": item.kind,
            "platform": item.platform,
            "pythonAbi": item.python_abi,
            "filename": item.filename,
            "size": item.size,
            "sha256": item.sha256,
        }
        for item in sorted(artifacts, key=lambda value: (value.kind, value.filename))
    ]
    payload.extend(
        {
            "kind": item.kind,
            "platform": item.platform,
            "pythonAbi": item.python_abi,
            "filename": item.filename,
            "size": item.size,
            "sha256": item.sha256,
        }
        for item in sorted(
            bundled_artifacts,
            key=lambda value: (value.kind, value.filename),
        )
    )
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def download_studio_artifact(
    artifact: StudioArtifact,
    destination: Path,
) -> Path:
    """Download one exact public object atomically and fail closed."""

    _validate_artifact_url(
        artifact.url,
        artifact.provider,
        artifact.sha256,
        artifact.filename,
    )
    if (
        destination.is_file()
        and destination.stat().st_size == artifact.size
        and _sha256(destination) == artifact.sha256
    ):
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_handle = tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=f".{destination.name}.{os.getpid()}.",
        suffix=".part",
        dir=destination.parent,
        delete=False,
    )
    temporary = Path(temporary_handle.name)
    temporary_handle.close()
    digest = hashlib.sha256()
    size = 0
    try:
        with urllib.request.urlopen(artifact.url, timeout=120) as response:
            final_url = str(getattr(response, "geturl", lambda: artifact.url)())
            _validate_artifact_url(
                final_url,
                artifact.provider,
                artifact.sha256,
                artifact.filename,
            )
            raw_length = response.headers.get("Content-Length")
            if raw_length is not None and int(raw_length) != artifact.size:
                raise ValueError("Studio artifact Content-Length is invalid.")
            with temporary.open("wb") as output:
                while chunk := response.read(_DOWNLOAD_CHUNK_BYTES):
                    size += len(chunk)
                    if size > artifact.size or size > _MAX_ARTIFACT_BYTES:
                        raise ValueError("Studio artifact size is invalid.")
                    output.write(chunk)
                    digest.update(chunk)
        if size != artifact.size or digest.hexdigest() != artifact.sha256:
            raise ValueError("Studio artifact checksum verification failed.")
        os.replace(temporary, destination)
        return destination
    except (OSError, TimeoutError, urllib.error.URLError, ValueError):
        temporary.unlink(missing_ok=True)
        raise


def probe_studio_artifact(artifact: StudioArtifact) -> None:
    """Verify anonymous provider-local access without downloading artifact bytes."""

    _validate_artifact_url(
        artifact.url,
        artifact.provider,
        artifact.sha256,
        artifact.filename,
    )
    request = urllib.request.Request(artifact.url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            final_url = str(getattr(response, "geturl", lambda: artifact.url)())
            _validate_artifact_url(
                final_url,
                artifact.provider,
                artifact.sha256,
                artifact.filename,
            )
            if (
                int(getattr(response, "status", 200) or 200) != 200
                or int(response.headers.get("Content-Length", 0) or 0) != artifact.size
            ):
                raise ValueError("Studio artifact public metadata is invalid.")
    except (OSError, TimeoutError, urllib.error.URLError, ValueError) as error:
        raise ValueError("Studio artifact is not publicly available.") from error


def _validate_artifact_url(
    url: str,
    provider: CloudProvider,
    sha256: str,
    filename: str,
) -> None:
    expected = studio_artifact_url(provider, sha256, filename)
    parsed = urllib.parse.urlsplit(url)
    if (
        url != expected
        or parsed.scheme != "https"
        or parsed.hostname != studio_artifact_host(provider)
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Studio artifact URL is invalid.")


def _validate_filename(filename: str) -> None:
    if not _FILENAME_PATTERN.fullmatch(filename) or Path(filename).name != filename:
        raise ValueError("Studio artifact filename is invalid.")


def _validate_sha256(value: str) -> None:
    if not _SHA256_PATTERN.fullmatch(value):
        raise ValueError("Studio artifact SHA-256 is invalid.")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(_DOWNLOAD_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "STUDIO_ARTIFACT_BUCKETS",
    "STUDIO_ARTIFACT_PREFIX",
    "STUDIO_BUNDLED_WHEELHOUSE",
    "STUDIO_RUNTIME_PLATFORM",
    "STUDIO_RUNTIME_PYTHON_ABI",
    "StudioArtifact",
    "StudioBundledArtifact",
    "StudioRuntimeManifest",
    "download_studio_artifact",
    "probe_studio_artifact",
    "runtime_epoch",
    "studio_artifact_base_url",
    "studio_artifact_host",
    "studio_artifact_key",
    "studio_artifact_url",
]
