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

"""TOS-backed durable state and VeFaaS IAM credential resolution."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from frontend.service.studio_release_server.models import (
    ReleaseServerSettings,
    ReleaseStatus,
    SourceUpload,
)

_IAM_CREDENTIAL_PATH = Path("/var/run/secrets/iam/credential")
_MAX_DEPENDENCY_WHEEL_BYTES = 128 * 1024 * 1024
_PYPI_FILE_HOST = "https://files.pythonhosted.org"
_PYPI_MIRROR_HOSTS = (
    "https://pypi.tuna.tsinghua.edu.cn",
    "https://mirrors.aliyun.com/pypi",
)


@dataclass(frozen=True)
class VolcengineCredentials:
    """One AK/SK pair with an optional STS token."""

    access_key: str
    secret_key: str
    session_token: str


def resolve_credentials() -> VolcengineCredentials:
    """Prefer explicit credentials locally, otherwise use VeFaaS IAM."""
    access_key = os.getenv("VOLCENGINE_ACCESS_KEY", "").strip()
    secret_key = os.getenv("VOLCENGINE_SECRET_KEY", "").strip()
    if bool(access_key) != bool(secret_key):
        raise ValueError("VOLCENGINE_ACCESS_KEY and VOLCENGINE_SECRET_KEY must match.")
    if access_key and secret_key:
        return VolcengineCredentials(
            access_key=access_key,
            secret_key=secret_key,
            session_token=os.getenv("VOLCENGINE_SESSION_TOKEN", "").strip(),
        )
    if not _IAM_CREDENTIAL_PATH.is_file():
        raise FileNotFoundError(
            "VeFaaS IAM credential file is unavailable and no AK/SK was provided."
        )
    payload = json.loads(_IAM_CREDENTIAL_PATH.read_text(encoding="utf-8"))
    return VolcengineCredentials(
        access_key=str(payload["access_key_id"]),
        secret_key=str(payload["secret_access_key"]),
        session_token=str(payload["session_token"]),
    )


class JobStore(Protocol):
    """Persistence contract used by the release orchestrator."""

    def get(self, job_id: str) -> ReleaseStatus | None:
        """Return one job, or None when it does not exist."""
        ...

    def put(self, status: ReleaseStatus) -> None:
        """Persist the complete current job state."""
        ...


class SourceStore(Protocol):
    """Create and consume private source archives used by release jobs."""

    def expected_key(self, job_id: str) -> str:
        """Return the only accepted source key for one job."""
        ...

    def prepare_upload(self, job_id: str) -> SourceUpload:
        """Return a short-lived upload target for one job."""
        ...

    def download_and_delete(
        self,
        source_key: str,
        destination: Path,
        *,
        max_bytes: int,
        on_progress: Callable[[int], None],
    ) -> None:
        """Download one source archive and remove its staging object."""
        ...


class DependencyStore(Protocol):
    """Materialize verified Studio dependency wheels from a durable cache."""

    def materialize(
        self,
        manifest: Path,
        destination: Path,
    ) -> tuple[Path, ...]:
        """Restore cached wheels, populating missing entries from their origin."""
        ...


class TosJobStore:
    """Persist release status independently of VeFaaS instances."""

    def __init__(
        self,
        settings: ReleaseServerSettings,
        *,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._settings = settings
        self._client_factory = client_factory or self._new_client

    def get(self, job_id: str) -> ReleaseStatus | None:
        """Load and validate one TOS status object."""
        import tos

        try:
            response = self._client_factory().get_object(
                bucket=self._settings.bucket,
                key=self._job_key(job_id),
            )
        except tos.exceptions.TosServerError as error:
            if error.status_code == 404:
                return None
            raise
        content = b"".join(response)
        if len(content) > 256 * 1024:
            raise ValueError("Studio release status object is too large.")
        return ReleaseStatus.model_validate_json(content)

    def put(self, status: ReleaseStatus) -> None:
        """Replace the mutable status object for one release job."""
        content = (
            json.dumps(status.public_dict(), ensure_ascii=False, indent=2) + "\n"
        ).encode()
        self._client_factory().put_object(
            bucket=self._settings.bucket,
            key=self._job_key(status.job_id),
            content=content,
            content_type="application/json",
        )

    def _job_key(self, job_id: str) -> str:
        return f"{self._settings.job_prefix.strip().strip('/')}/{job_id}.json"

    def _new_client(self) -> Any:
        import tos

        credentials = resolve_credentials()
        return tos.TosClientV2(
            credentials.access_key,
            credentials.secret_key,
            security_token=credentials.session_token or None,
            endpoint=f"tos-{self._settings.region}.volces.com",
            region=self._settings.region,
        )


class TosSourceStore:
    """Stage Git archives through signed TOS URLs without sharing credentials."""

    def __init__(
        self,
        settings: ReleaseServerSettings,
        *,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._settings = settings
        self._client_factory = client_factory or self._new_client

    def expected_key(self, job_id: str) -> str:
        prefix = self._settings.job_prefix.strip().strip("/")
        return f"{prefix}/sources/{job_id}.tar.gz"

    def prepare_upload(self, job_id: str) -> SourceUpload:
        import tos

        source_key = self.expected_key(job_id)
        signed = self._client_factory().pre_signed_url(
            tos.HttpMethodType.Http_Method_Put,
            bucket=self._settings.bucket,
            key=source_key,
            expires=900,
        )
        return SourceUpload(
            sourceKey=source_key,
            uploadUrl=signed.signed_url,
            expiresIn=900,
        )

    def download_and_delete(
        self,
        source_key: str,
        destination: Path,
        *,
        max_bytes: int,
        on_progress: Callable[[int], None],
    ) -> None:
        client = self._client_factory()
        response = client.get_object(
            bucket=self._settings.bucket,
            key=source_key,
        )
        size = 0
        with destination.open("wb") as output:
            for chunk in response:
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError("Staged source archive exceeds 200 MiB.")
                output.write(chunk)
                on_progress(size)
        client.delete_object(
            bucket=self._settings.bucket,
            key=source_key,
        )

    def _new_client(self) -> Any:
        import tos

        credentials = resolve_credentials()
        return tos.TosClientV2(
            credentials.access_key,
            credentials.secret_key,
            security_token=credentials.session_token or None,
            endpoint=f"tos-{self._settings.region}.volces.com",
            region=self._settings.region,
        )


class TosDependencyStore:
    """Cache pinned Studio wheels in TOS by their immutable checksum."""

    def __init__(
        self,
        settings: ReleaseServerSettings,
        *,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._settings = settings
        self._client_factory = client_factory or self._new_client

    def materialize(
        self,
        manifest: Path,
        destination: Path,
    ) -> tuple[Path, ...]:
        """Restore every verified wheel, downloading only cache misses."""
        wheels = self._load_manifest(manifest)
        destination.mkdir(parents=True, exist_ok=True)
        client = self._client_factory()
        staged: list[Path] = []
        for filename, url, sha256 in wheels:
            key = self._cache_key(filename, sha256)
            content = self._get_cached(client, key, sha256)
            if content is None:
                content = self._download(url, sha256)
                client.put_object(
                    bucket=self._settings.bucket,
                    key=key,
                    content=content,
                    content_type="application/octet-stream",
                )
            target = destination / filename
            target.write_bytes(content)
            staged.append(target)
        return tuple(staged)

    def _load_manifest(self, manifest: Path) -> tuple[tuple[str, str, str], ...]:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        raw_wheels = payload.get("wheels") if isinstance(payload, dict) else None
        if not isinstance(raw_wheels, list) or not raw_wheels or len(raw_wheels) > 32:
            raise ValueError("Studio dependency manifest is invalid.")
        wheels: list[tuple[str, str, str]] = []
        for raw in raw_wheels:
            if not isinstance(raw, dict):
                raise ValueError("Studio dependency manifest is invalid.")
            filename = raw.get("filename")
            url = raw.get("url")
            sha256 = raw.get("sha256")
            if (
                not isinstance(filename, str)
                or Path(filename).name != filename
                or not filename.endswith(".whl")
                or not isinstance(url, str)
                or not url.startswith("https://")
                or not isinstance(sha256, str)
                or len(sha256) != 64
            ):
                raise ValueError("Studio dependency manifest is invalid.")
            try:
                int(sha256, 16)
            except ValueError as error:
                raise ValueError("Studio dependency manifest is invalid.") from error
            wheels.append((filename, url, sha256.lower()))
        return tuple(wheels)

    def _cache_key(self, filename: str, sha256: str) -> str:
        prefix = self._settings.job_prefix.strip().strip("/")
        return f"{prefix}/dependency-cache/{sha256}/{filename}"

    def _get_cached(self, client: Any, key: str, sha256: str) -> bytes | None:
        try:
            response = client.get_object(bucket=self._settings.bucket, key=key)
        except Exception as error:  # noqa: BLE001
            if getattr(error, "status_code", None) == 404:
                return None
            raise
        content = self._read_limited(response)
        if hashlib.sha256(content).hexdigest() != sha256:
            return None
        return content

    def _download(self, url: str, sha256: str) -> bytes:
        last_error: OSError | ValueError | None = None
        for candidate in self._download_urls(url):
            try:
                with urllib.request.urlopen(candidate, timeout=120) as response:
                    content = response.read(_MAX_DEPENDENCY_WHEEL_BYTES + 1)
                if len(content) > _MAX_DEPENDENCY_WHEEL_BYTES:
                    raise ValueError("Studio dependency wheel exceeds 128 MiB.")
                if hashlib.sha256(content).hexdigest() != sha256:
                    raise ValueError(
                        "Studio dependency wheel checksum verification failed."
                    )
                return content
            except (OSError, ValueError) as error:
                last_error = error
        if last_error is None:
            raise RuntimeError("Studio dependency wheel has no download source.")
        raise last_error

    def _download_urls(self, url: str) -> tuple[str, ...]:
        if not url.startswith(f"{_PYPI_FILE_HOST}/packages/"):
            return (url,)
        path = url.removeprefix(_PYPI_FILE_HOST)
        return tuple(f"{host}{path}" for host in _PYPI_MIRROR_HOSTS) + (url,)

    def _read_limited(self, response: Any) -> bytes:
        content = bytearray()
        for chunk in response:
            if len(content) + len(chunk) > _MAX_DEPENDENCY_WHEEL_BYTES:
                raise ValueError("Cached Studio dependency wheel exceeds 128 MiB.")
            content.extend(chunk)
        return bytes(content)

    def _new_client(self) -> Any:
        import tos

        credentials = resolve_credentials()
        return tos.TosClientV2(
            credentials.access_key,
            credentials.secret_key,
            security_token=credentials.session_token or None,
            endpoint=f"tos-{self._settings.region}.volces.com",
            region=self._settings.region,
        )


__all__ = [
    "DependencyStore",
    "JobStore",
    "SourceStore",
    "TosDependencyStore",
    "TosJobStore",
    "TosSourceStore",
    "VolcengineCredentials",
    "resolve_credentials",
]
