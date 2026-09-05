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

"""Resolve and securely bootstrap the pinned native AgentKit CLI."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
from importlib import import_module, metadata
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from typing import Any

AGENTKIT_CLI_VERSION = "0.52.14"
# Direct bootstrap uses the one verified public upstream. Provider-local Studio
# bundles materialize this archive through their signed runtime manifest instead.
AGENTKIT_CLI_RELEASE_HOST = "agentkit-cli.tos-cn-beijing.volces.com"
AGENTKIT_CLI_RELEASE_BASE = f"https://{AGENTKIT_CLI_RELEASE_HOST}"
AGENTKIT_CLI_ENV = "VEADK_AGENTKIT_CLI"
AGENTKIT_CLI_CACHE_ENV = "VEADK_AGENTKIT_CLI_CACHE"
AGENTKIT_CLI_COMPANION_DISTRIBUTION = "volcengine-agentkit-cli-bin"

_DOWNLOAD_TIMEOUT_SECONDS = 30
_DOWNLOAD_ATTEMPTS = 3
_DOWNLOAD_CHUNK_BYTES = 1024 * 1024
_MAX_ARCHIVE_BYTES = 80 * 1024 * 1024
_MAX_EXTRACTED_BYTES = 300 * 1024 * 1024
_MAX_ARCHIVE_MEMBERS = 10_000
_LOCK_TIMEOUT_SECONDS = 120
_VERSION_TIMEOUT_SECONDS = 15
_VERSION_TOKEN = re.compile(
    rf"(?<![A-Za-z0-9.!+_-]){re.escape(AGENTKIT_CLI_VERSION)}" r"(?![A-Za-z0-9.!+_-])"
)


class AgentKitCliError(RuntimeError):
    """Raised when the pinned AgentKit CLI cannot be resolved safely."""


@dataclass(frozen=True)
class AgentKitCliArtifact:
    """One immutable native CLI release artifact."""

    platform_key: str
    filename: str
    sha256: str
    archive_root: str
    executable_name: str

    @property
    def url(self) -> str:
        return f"{AGENTKIT_CLI_RELEASE_BASE}/{AGENTKIT_CLI_VERSION}/{self.filename}"


AGENTKIT_CLI_ARTIFACTS = {
    "linux-x64": AgentKitCliArtifact(
        platform_key="linux-x64",
        filename="agentkit-linux-x64.tar.gz",
        sha256="4e76e32c60473b5037c331a7c74bb99b1c23b62eb8ce26379d3a8c41af38a64e",
        archive_root=f"agentkit-{AGENTKIT_CLI_VERSION}-linux-x64",
        executable_name="ak",
    ),
    "linux-arm64": AgentKitCliArtifact(
        platform_key="linux-arm64",
        filename="agentkit-linux-arm64.tar.gz",
        sha256="cbd9af81c6f591ef677a296ebb905ed11a3bfc09808362a656fba3e9e2d8f430",
        archive_root=f"agentkit-{AGENTKIT_CLI_VERSION}-linux-arm64",
        executable_name="ak",
    ),
    "darwin-x64": AgentKitCliArtifact(
        platform_key="darwin-x64",
        filename="agentkit-darwin-x64.tar.gz",
        sha256="4b775f760b8e5fd8302e9eb92e7ac21aa28b284d5d76a649778c136732285e2e",
        archive_root=f"agentkit-{AGENTKIT_CLI_VERSION}-darwin-x64",
        executable_name="ak",
    ),
    "darwin-arm64": AgentKitCliArtifact(
        platform_key="darwin-arm64",
        filename="agentkit-darwin-arm64.tar.gz",
        sha256="c282b707f025d5732d114220a6956004762dd58abe39f4ccaaf360b73f80c480",
        archive_root=f"agentkit-{AGENTKIT_CLI_VERSION}-darwin-arm64",
        executable_name="ak",
    ),
    "windows-x64": AgentKitCliArtifact(
        platform_key="windows-x64",
        filename="agentkit-windows-x64.zip",
        sha256="4737ff064edf73eb3901d485e3f543a88a916e39e44efd1aca5681fc89af6665",
        archive_root=f"agentkit-{AGENTKIT_CLI_VERSION}-windows-x64",
        executable_name="ak.exe",
    ),
}


def agentkit_cli_artifact(
    *,
    system: str | None = None,
    machine: str | None = None,
) -> AgentKitCliArtifact:
    """Return the pinned artifact for the current supported platform."""

    normalized_system = (system or platform.system()).strip().lower()
    normalized_machine = (machine or platform.machine()).strip().lower()
    system_key = {
        "linux": "linux",
        "darwin": "darwin",
        "windows": "windows",
    }.get(normalized_system)
    architecture_key = {
        "amd64": "x64",
        "x86_64": "x64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(normalized_machine)
    platform_key = (
        f"{system_key}-{architecture_key}"
        if system_key is not None and architecture_key is not None
        else ""
    )
    artifact = AGENTKIT_CLI_ARTIFACTS.get(platform_key)
    if artifact is None:
        raise AgentKitCliError(
            "AgentKit CLI is not available for platform "
            f"{normalized_system or 'unknown'}/{normalized_machine or 'unknown'}."
        )
    return artifact


def default_agentkit_cli_cache_root() -> Path:
    """Return the per-user cache root without mutating PATH."""

    configured = os.getenv(AGENTKIT_CLI_CACHE_ENV, "").strip()
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA", "").strip()
        if base:
            return Path(base) / "VeADK" / "Cache" / "agentkit-cli"
    xdg_cache = os.getenv("XDG_CACHE_HOME", "").strip()
    base = Path(xdg_cache).expanduser() if xdg_cache else Path.home() / ".cache"
    return base / "veadk" / "agentkit-cli"


def cached_agentkit_cli_path(
    artifact: AgentKitCliArtifact | None = None,
    *,
    cache_root: Path | None = None,
) -> Path:
    """Return the immutable cache location for one platform executable."""

    selected = artifact or agentkit_cli_artifact()
    root = cache_root or default_agentkit_cli_cache_root()
    return (
        root / AGENTKIT_CLI_VERSION / selected.platform_key / selected.executable_name
    )


def validate_agentkit_cli_executable(executable: str | Path) -> bool:
    """Return whether an executable reports the exact pinned CLI version."""

    path = Path(executable)
    if not path.is_file() or (os.name != "nt" and not os.access(path, os.X_OK)):
        return False
    try:
        completed = subprocess.run(
            [str(path), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=_VERSION_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    reported = f"{completed.stdout}\n{completed.stderr}"
    return completed.returncode == 0 and _VERSION_TOKEN.search(reported) is not None


def resolve_agentkit_cli(
    *,
    archive: Path | None = None,
    cache_root: Path | None = None,
    allow_download: bool = True,
) -> Path:
    """Resolve the pinned CLI, preferring an explicit immutable archive."""

    if archive is not None:
        artifact = agentkit_cli_artifact()
        verify_agentkit_cli_archive(archive, artifact)
        return install_agentkit_cli(
            artifact=artifact,
            archive=archive,
            cache_root=cache_root,
        )

    configured = os.getenv(AGENTKIT_CLI_ENV, "").strip()
    if configured:
        configured_path = shutil.which(configured)
        if configured_path is None or not validate_agentkit_cli_executable(
            configured_path
        ):
            raise AgentKitCliError(
                f"{AGENTKIT_CLI_ENV} does not reference AgentKit CLI "
                f"{AGENTKIT_CLI_VERSION}."
            )
        return Path(configured_path)

    companion = _compatible_companion_executable()
    if companion is not None:
        return companion

    path_candidate = shutil.which("ak")
    if path_candidate and validate_agentkit_cli_executable(path_candidate):
        return Path(path_candidate)

    artifact = agentkit_cli_artifact()
    cached = cached_agentkit_cli_path(artifact, cache_root=cache_root)
    if validate_agentkit_cli_executable(cached):
        return cached
    if archive is None and not allow_download:
        raise AgentKitCliError(
            f"AgentKit CLI {AGENTKIT_CLI_VERSION} is not installed or cached."
        )
    return install_agentkit_cli(
        artifact=artifact,
        archive=archive,
        cache_root=cache_root,
    )


def install_agentkit_cli(
    *,
    artifact: AgentKitCliArtifact | None = None,
    archive: Path | None = None,
    cache_root: Path | None = None,
) -> Path:
    """Install one verified archive into the immutable per-user cache."""

    selected = artifact or agentkit_cli_artifact()
    root = cache_root or default_agentkit_cli_cache_root()
    target = cached_agentkit_cli_path(selected, cache_root=root).parent
    lock_path = root / AGENTKIT_CLI_VERSION / f".{selected.platform_key}.lock"
    with _exclusive_lock(lock_path):
        executable = target / selected.executable_name
        if validate_agentkit_cli_executable(executable):
            return executable
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=f".{selected.platform_key}-", dir=target.parent
        ) as tmp:
            workspace = Path(tmp)
            resolved_archive = archive
            if resolved_archive is None:
                resolved_archive = workspace / selected.filename
                download_agentkit_cli_archive(resolved_archive, selected)
            _verify_archive(resolved_archive, selected)
            extracted = workspace / "extracted"
            extracted.mkdir()
            _extract_archive(resolved_archive, extracted, selected)
            extracted_root = extracted / selected.archive_root
            candidate = extracted_root / selected.executable_name
            if not validate_agentkit_cli_executable(candidate):
                raise AgentKitCliError(
                    "AgentKit CLI archive executable does not report the pinned version."
                )
            os.replace(extracted_root, target)
        if not validate_agentkit_cli_executable(executable):
            if target.exists():
                shutil.rmtree(target)
            raise AgentKitCliError(
                "AgentKit CLI cache validation failed after install."
            )
        return executable


def download_agentkit_cli_archive(
    destination: Path,
    artifact: AgentKitCliArtifact | None = None,
) -> Path:
    """Download one fixed-host archive with bounded retries and exact SHA256."""

    selected = artifact or agentkit_cli_artifact()
    _validate_release_url(selected.url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(_DOWNLOAD_ATTEMPTS):
        temporary = destination.with_name(f".{destination.name}.{os.getpid()}.part")
        temporary.unlink(missing_ok=True)
        try:
            digest = hashlib.sha256()
            size = 0
            with _open_release_url(selected.url) as response:
                final_url = str(getattr(response, "geturl", lambda: selected.url)())
                _validate_release_url(final_url)
                raw_length = response.headers.get("Content-Length")
                if raw_length:
                    try:
                        declared_length = int(raw_length)
                    except ValueError as error:
                        raise AgentKitCliError(
                            "AgentKit CLI archive has an invalid Content-Length."
                        ) from error
                    if declared_length <= 0 or declared_length > _MAX_ARCHIVE_BYTES:
                        raise AgentKitCliError(
                            "AgentKit CLI archive exceeds the download size limit."
                        )
                with temporary.open("wb") as output:
                    while chunk := response.read(_DOWNLOAD_CHUNK_BYTES):
                        size += len(chunk)
                        if size > _MAX_ARCHIVE_BYTES:
                            raise AgentKitCliError(
                                "AgentKit CLI archive exceeds the download size limit."
                            )
                        output.write(chunk)
                        digest.update(chunk)
            if size <= 0 or digest.hexdigest() != selected.sha256:
                raise AgentKitCliError(
                    "AgentKit CLI archive checksum verification failed."
                )
            os.replace(temporary, destination)
            return destination
        except AgentKitCliError:
            temporary.unlink(missing_ok=True)
            raise
        except (OSError, TimeoutError, urllib.error.URLError) as error:
            temporary.unlink(missing_ok=True)
            last_error = error
            if attempt + 1 < _DOWNLOAD_ATTEMPTS:
                time.sleep(attempt + 1)
    raise AgentKitCliError(
        "Could not download the pinned AgentKit CLI archive."
    ) from last_error


def verify_agentkit_cli_archive(
    archive: Path,
    artifact: AgentKitCliArtifact | None = None,
) -> None:
    """Validate the exact archive bytes without extracting them."""

    _verify_archive(archive, artifact or agentkit_cli_artifact())


def _compatible_companion_executable() -> Path | None:
    try:
        if (
            metadata.version(AGENTKIT_CLI_COMPANION_DISTRIBUTION)
            != AGENTKIT_CLI_VERSION
        ):
            return None
        companion = import_module("volcengine_agentkit_cli_bin")
        resolver = getattr(companion, "executable", None)
        if not callable(resolver):
            return None
        resolved = resolver()
    except (ImportError, metadata.PackageNotFoundError, OSError, RuntimeError):
        return None
    if not isinstance(resolved, str) or not resolved:
        return None
    path = Path(resolved)
    return path if validate_agentkit_cli_executable(path) else None


def _verify_archive(archive: Path, artifact: AgentKitCliArtifact) -> None:
    try:
        size = archive.stat().st_size
    except OSError as error:
        raise AgentKitCliError("AgentKit CLI archive is unavailable.") from error
    if size <= 0 or size > _MAX_ARCHIVE_BYTES:
        raise AgentKitCliError("AgentKit CLI archive size is invalid.")
    digest = hashlib.sha256()
    try:
        with archive.open("rb") as source:
            while chunk := source.read(_DOWNLOAD_CHUNK_BYTES):
                digest.update(chunk)
    except OSError as error:
        raise AgentKitCliError("AgentKit CLI archive cannot be read.") from error
    if digest.hexdigest() != artifact.sha256:
        raise AgentKitCliError("AgentKit CLI archive checksum verification failed.")


def _extract_archive(
    archive: Path,
    destination: Path,
    artifact: AgentKitCliArtifact,
) -> None:
    try:
        if artifact.filename.endswith(".zip"):
            _extract_zip(archive, destination, artifact)
        else:
            _extract_tar(archive, destination, artifact)
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        raise AgentKitCliError("AgentKit CLI archive is invalid.") from error


def _safe_member_path(name: str, artifact: AgentKitCliArtifact) -> tuple[str, ...]:
    if "\\" in name:
        raise AgentKitCliError("AgentKit CLI archive contains an unsafe path.")
    path = PurePosixPath(name)
    parts = tuple(part for part in path.parts if part != ".")
    if (
        path.is_absolute()
        or not parts
        or any(part in {"", ".."} for part in parts)
        or parts[0] != artifact.archive_root
    ):
        raise AgentKitCliError("AgentKit CLI archive contains an unsafe path.")
    return parts


def _extract_tar(
    archive_path: Path,
    destination: Path,
    artifact: AgentKitCliArtifact,
) -> None:
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        if not members or len(members) > _MAX_ARCHIVE_MEMBERS:
            raise AgentKitCliError("AgentKit CLI archive member count is invalid.")
        total_size = 0
        for member in members:
            parts = _safe_member_path(member.name, artifact)
            if not (member.isdir() or member.isreg()):
                raise AgentKitCliError(
                    "AgentKit CLI archive contains a link or special file."
                )
            total_size += member.size
            if total_size > _MAX_EXTRACTED_BYTES:
                raise AgentKitCliError(
                    "AgentKit CLI archive is too large when extracted."
                )
            target = destination.joinpath(*parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise AgentKitCliError("AgentKit CLI archive member is invalid.")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(member.mode & 0o777)


def _extract_zip(
    archive_path: Path,
    destination: Path,
    artifact: AgentKitCliArtifact,
) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if not members or len(members) > _MAX_ARCHIVE_MEMBERS:
            raise AgentKitCliError("AgentKit CLI archive member count is invalid.")
        total_size = 0
        for member in members:
            parts = _safe_member_path(member.filename, artifact)
            mode = member.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            if file_type not in {0, stat.S_IFDIR, stat.S_IFREG}:
                raise AgentKitCliError(
                    "AgentKit CLI archive contains a link or special file."
                )
            total_size += member.file_size
            if total_size > _MAX_EXTRACTED_BYTES:
                raise AgentKitCliError(
                    "AgentKit CLI archive is too large when extracted."
                )
            target = destination.joinpath(*parts)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            if mode:
                target.chmod(mode & 0o777)


class _PinnedHostRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        _validate_release_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _validate_release_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != AGENTKIT_CLI_RELEASE_HOST
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
    ):
        raise AgentKitCliError(
            "AgentKit CLI download must remain on the pinned HTTPS release host."
        )


def _open_release_url(url: str) -> Any:
    opener = urllib.request.build_opener(_PinnedHostRedirectHandler())
    request = urllib.request.Request(url, headers={"User-Agent": "veadk-agentkit-cli"})
    return opener.open(request, timeout=_DOWNLOAD_TIMEOUT_SECONDS)


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as error:
                if time.monotonic() >= deadline:
                    raise AgentKitCliError(
                        "Timed out waiting for the AgentKit CLI installation lock."
                    ) from error
                time.sleep(0.1)
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


__all__ = [
    "AGENTKIT_CLI_ARTIFACTS",
    "AGENTKIT_CLI_CACHE_ENV",
    "AGENTKIT_CLI_ENV",
    "AGENTKIT_CLI_RELEASE_BASE",
    "AGENTKIT_CLI_RELEASE_HOST",
    "AGENTKIT_CLI_VERSION",
    "AgentKitCliArtifact",
    "AgentKitCliError",
    "agentkit_cli_artifact",
    "cached_agentkit_cli_path",
    "default_agentkit_cli_cache_root",
    "download_agentkit_cli_archive",
    "install_agentkit_cli",
    "resolve_agentkit_cli",
    "validate_agentkit_cli_executable",
    "verify_agentkit_cli_archive",
]
