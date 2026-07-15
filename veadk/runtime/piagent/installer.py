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

"""Resolve or install the local Pi runtime distribution."""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import stat
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_REPO = "earendil-works/pi"


class PiAgentInstallError(RuntimeError):
    """Raised when the Pi binary cannot be found or installed."""


def resolve_or_install_piagent_binary() -> str:
    """Return an executable Pi binary path, installing it when needed.

    Resolution is intentionally explicit and deterministic:

    1. ``PIAGENT_BINARY`` points at a user-provided executable.
    2. ``PIAGENT_INSTALL_DIR/pi/pi`` is used as the managed cache.
    3. Otherwise the Pi archive is downloaded and installed into that cache.
    """

    configured = os.getenv("PIAGENT_BINARY")
    if configured:
        return _validate_executable(Path(configured).expanduser(), "PIAGENT_BINARY")

    install_dir = _install_dir()
    binary = _installed_binary_path(install_dir)
    if _is_executable(binary):
        return str(binary)

    url, archive_name = _resolve_download_url()
    logger.info(f"piagent runtime: installing Pi binary from {url}")
    try:
        archive_path = _download(url, archive_name)
        expected_sha256 = os.getenv("PIAGENT_BINARY_SHA256")
        if expected_sha256:
            _verify_sha256(archive_path, expected_sha256)
        _install_archive(archive_path, install_dir)
    except Exception as e:  # noqa: BLE001
        raise PiAgentInstallError(
            f"Failed to install the Pi binary from {url} into {install_dir}: {e}. "
            "Set PIAGENT_BINARY to an existing executable, or set "
            "PIAGENT_BINARY_URL/PIAGENT_BINARY_SHA256 to a reachable archive. "
            "For AgentKit deployments, preinstall Pi in the image and set "
            "PIAGENT_BINARY to that path."
        ) from e

    return _validate_executable(binary, "installed Pi binary")


def _install_dir() -> Path:
    return Path(os.getenv("PIAGENT_INSTALL_DIR", "~/.cache/veadk/piagent")).expanduser()


def _installed_binary_path(install_dir: Path) -> Path:
    return install_dir / "pi" / _binary_name()


def _validate_executable(path: Path, source: str) -> str:
    if not path.exists():
        raise PiAgentInstallError(f"{source} points to missing file: {path}")
    if not _is_executable(path):
        raise PiAgentInstallError(f"{source} is not executable: {path}")
    return str(path)


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _binary_name() -> str:
    return "pi.exe" if platform.system().lower() == "windows" else "pi"


def _resolve_download_url() -> tuple[str, str]:
    explicit = os.getenv("PIAGENT_BINARY_URL")
    platform_key, archive_name = resolve_platform_archive()
    if explicit:
        return explicit, Path(explicit.split("?", 1)[0]).name or archive_name

    version = os.getenv("PIAGENT_BINARY_VERSION", "latest").strip()
    if not version:
        version = "latest"
    if version == "latest":
        tag = "latest"
    else:
        tag = version if version.startswith("v") else f"v{version}"

    repo = os.getenv("PIAGENT_BINARY_REPO", _DEFAULT_REPO)
    if tag == "latest":
        url = f"https://github.com/{repo}/releases/latest/download/{archive_name}"
    else:
        url = f"https://github.com/{repo}/releases/download/{tag}/{archive_name}"

    logger.debug(
        f"piagent runtime: resolved platform {platform_key} to archive {archive_name}"
    )
    return url, archive_name


def resolve_platform_archive() -> tuple[str, str]:
    """Return normalized platform key and expected Pi release archive name."""

    requested = os.getenv("PIAGENT_BINARY_PLATFORM")
    if requested:
        normalized = requested.strip().lower().replace("_", "-")
    else:
        system = platform.system().lower()
        machine = platform.machine().lower()
        arch = {
            "x86_64": "amd64",
            "amd64": "amd64",
            "aarch64": "arm64",
            "arm64": "arm64",
        }.get(machine, machine)
        normalized = f"{system}/{arch}"

    aliases = {
        "linux/amd64": ("linux/amd64", "pi-linux-x64.tar.gz"),
        "linux-x64": ("linux/amd64", "pi-linux-x64.tar.gz"),
        "linux/arm64": ("linux/arm64", "pi-linux-arm64.tar.gz"),
        "linux-aarch64": ("linux/arm64", "pi-linux-arm64.tar.gz"),
        "darwin/amd64": ("darwin/amd64", "pi-darwin-x64.tar.gz"),
        "darwin-x64": ("darwin/amd64", "pi-darwin-x64.tar.gz"),
        "darwin/arm64": ("darwin/arm64", "pi-darwin-arm64.tar.gz"),
        "darwin-aarch64": ("darwin/arm64", "pi-darwin-arm64.tar.gz"),
        "windows/amd64": ("windows/amd64", "pi-windows-x64.zip"),
        "windows-x64": ("windows/amd64", "pi-windows-x64.zip"),
    }
    try:
        return aliases[normalized]
    except KeyError as e:
        raise PiAgentInstallError(
            f"Unsupported PIAGENT_BINARY_PLATFORM {requested or normalized!r}. "
            "Supported values include linux/amd64 and linux/arm64; set "
            "PIAGENT_BINARY_URL for a custom archive."
        ) from e


def _download(url: str, archive_name: str) -> Path:
    tmp_dir = Path(tempfile.mkdtemp(prefix="veadk-piagent-download-"))
    archive_path = tmp_dir / archive_name
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
        with archive_path.open("wb") as out:
            shutil.copyfileobj(response, out)
    return archive_path


def _verify_sha256(path: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual.lower() != expected.strip().lower():
        raise PiAgentInstallError(
            f"sha256 mismatch for {path.name}: expected {expected}, got {actual}"
        )


def _install_archive(archive_path: Path, install_dir: Path) -> None:
    extract_dir = Path(tempfile.mkdtemp(prefix="veadk-piagent-extract-"))
    if tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path) as tar:
            _safe_extract_tar(tar, extract_dir)
    elif zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as zf:
            _safe_extract_zip(zf, extract_dir)
    else:
        bundle_dir = extract_dir / "pi"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(archive_path, bundle_dir / _binary_name())

    candidate = _find_binary(extract_dir)
    if candidate is None:
        raise PiAgentInstallError(
            f"archive does not contain a pi executable: {archive_path}"
        )

    source_dir = candidate.parent
    target_dir = install_dir / "pi"
    install_dir.mkdir(parents=True, exist_ok=True)
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(source_dir, target_dir)

    target = _installed_binary_path(install_dir)
    mode = target.stat().st_mode
    target.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _find_binary(root: Path) -> Path | None:
    names = {_binary_name(), "pi", "piagent", "pi.exe"}
    for path in root.rglob("*"):
        if path.is_file() and path.name in names:
            return path
    return None


def _safe_extract_tar(tar: tarfile.TarFile, extract_dir: Path) -> None:
    root = extract_dir.resolve()
    for member in tar.getmembers():
        destination = (extract_dir / member.name).resolve()
        if root != destination and root not in destination.parents:
            raise PiAgentInstallError(f"unsafe archive member path: {member.name}")
        if member.isdir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        if not member.isfile():
            continue
        source = tar.extractfile(member)
        if source is None:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        with source, destination.open("wb") as out:
            shutil.copyfileobj(source, out)


def _safe_extract_zip(zf: zipfile.ZipFile, extract_dir: Path) -> None:
    root = extract_dir.resolve()
    for member in zf.infolist():
        destination = (extract_dir / member.filename).resolve()
        if root != destination and root not in destination.parents:
            raise PiAgentInstallError(f"unsafe archive member path: {member.filename}")
        if member.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member) as source, destination.open("wb") as out:
            shutil.copyfileobj(source, out)
