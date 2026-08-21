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

"""Fetch an exact GitHub revision and publish its Studio release."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from frontend.service.studio_release_server.models import (
    BuildResult,
    ReleaseRequest,
    ReleaseServerSettings,
)
from frontend.service.studio_release_server.tos_store import (
    DependencyStore,
    SourceStore,
    resolve_credentials,
)

_MAX_SOURCE_ARCHIVE_BYTES = 200 * 1024 * 1024
_MAX_SOURCE_EXTRACTED_BYTES = 1024 * 1024 * 1024
_MAX_SOURCE_ARCHIVE_MEMBERS = 50_000
_SOURCE_DOWNLOAD_REPORT_BYTES = 8 * 1024 * 1024
_SOURCE_DOWNLOAD_ATTEMPT_SECONDS = 120
_GITHUB_ARCHIVE_MIRROR = "https://ghfast.top/https://github.com"
_GITHUB_CLONE_MIRROR = "https://ghfast.top/https://github.com"
_GIT_CLONE_ATTEMPT_SECONDS = 30
_SPARSE_CHECKOUT_PATHS = (
    "/pyproject.toml",
    "/README.md",
    "/LICENSE",
    "/frontend/",
    "/veadk/",
    "!/veadk/webui/",
)
_NODE_VERSION = "22.17.0"
_NODE_DOWNLOAD_BASE_URLS = (
    "https://registry.npmmirror.com/-/binary/node",
    "https://nodejs.org/dist",
)
_NPM_REGISTRY = "https://registry.npmmirror.com"
_PYPI_SIMPLE_INDEX = "https://mirrors.aliyun.com/pypi/simple/"
_NODE_ARCHIVE_SHA256 = {
    "arm64": "140aee84be6774f5fb3f404be72adbe8420b523f824de82daeb5ab218dab7b18",
    "x64": "325c0f1261e0c61bcae369a1274028e9cfb7ab7949c05512c5b1e630f7e80e12",
}
_CGROUP_MEMORY_LIMIT_PATHS = (
    Path("/sys/fs/cgroup/memory.max"),
    Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
)
_NODE_HEAP_MEMORY_RATIO = 0.75
_DEFAULT_NODE_HEAP_MB = 4096

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str], None]


def _physical_memory_bytes() -> int | None:
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        page_count = os.sysconf("SC_PHYS_PAGES")
    except (OSError, ValueError):
        return None
    if page_size <= 0 or page_count <= 0:
        return None
    return page_size * page_count


def _memory_limit_bytes(
    *,
    cgroup_paths: tuple[Path, ...] = _CGROUP_MEMORY_LIMIT_PATHS,
    physical_memory: int | None = None,
) -> int | None:
    if physical_memory is None:
        physical_memory = _physical_memory_bytes()
    candidates = [physical_memory] if physical_memory and physical_memory > 0 else []
    for path in cgroup_paths:
        try:
            raw_limit = path.read_text(encoding="utf-8").strip()
            cgroup_limit = int(raw_limit)
        except (FileNotFoundError, OSError, ValueError):
            continue
        if cgroup_limit <= 0:
            continue
        # Cgroup v1 represents an unlimited value with a number close to 2^63.
        if physical_memory and cgroup_limit > physical_memory:
            continue
        candidates.append(cgroup_limit)
    return min(candidates) if candidates else None


def _node_heap_limit_mb(memory_limit: int | None = None) -> int:
    if memory_limit is None:
        memory_limit = _memory_limit_bytes()
    if memory_limit is None:
        return _DEFAULT_NODE_HEAP_MB
    return max(128, int(memory_limit * _NODE_HEAP_MEMORY_RATIO / (1024 * 1024)))


def _node_options(existing: str, heap_limit_mb: int) -> str:
    try:
        options = shlex.split(existing)
    except ValueError:
        options = []
    filtered: list[str] = []
    skip_value = False
    for option in options:
        if skip_value:
            skip_value = False
            continue
        normalized = option.replace("_", "-")
        if normalized == "--max-old-space-size":
            skip_value = True
            continue
        if normalized.startswith("--max-old-space-size="):
            continue
        filtered.append(option)
    filtered.append(f"--max-old-space-size={heap_limit_mb}")
    return shlex.join(filtered)


class ReleaseBuilder(Protocol):
    """Build boundary injected into the release orchestrator."""

    def build(
        self,
        request: ReleaseRequest,
        on_progress: ProgressCallback,
    ) -> BuildResult:
        """Build, publish, and verify one release."""
        ...


class StudioReleaseBuilder:
    """Build Studio from a GitHub commit in an isolated workspace."""

    def __init__(
        self,
        settings: ReleaseServerSettings,
        *,
        source_store: SourceStore | None = None,
        dependency_store: DependencyStore | None = None,
    ) -> None:
        self._settings = settings
        self._source_store = source_store
        self._dependency_store = dependency_store

    def build(
        self,
        request: ReleaseRequest,
        on_progress: ProgressCallback,
    ) -> BuildResult:
        """Download source, invoke the repository publisher, and verify latest."""
        total_started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="studio_release_job_") as tmp:
            workspace = Path(tmp)
            fetch_started = time.monotonic()
            on_progress("fetching", "正在按 Git SHA 拉取 GitHub 源码")
            source_root = self._download_source(request, workspace, on_progress)
            fetch_seconds = time.monotonic() - fetch_started

            prepared_root = source_root / ".studio-release"
            frontend_assets = prepared_root / "frontend"
            dependency_wheels = self._prepare_dependency_wheels(
                source_root,
                prepared_root,
                workspace,
                on_progress,
            )
            tools_started = time.monotonic()
            if (frontend_assets / "index.html").is_file():
                on_progress("preparing", "正在校验预构建前端与依赖包")
                node_bin = None
            else:
                on_progress("preparing", "正在准备 Node 与 uv 构建工具")
                node_bin = self._ensure_node()
            uv = shutil.which("uv")
            if uv is None:
                raise RuntimeError("uv is not installed in the release server package.")
            tools_seconds = time.monotonic() - tools_started

            version = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d%H%M%S")
            output_dir = workspace / "dist"
            publish_started = time.monotonic()
            on_progress("building", "正在构建 Studio Bundle 并发布到 TOS")
            self._run_publisher(
                request=request,
                source_root=source_root,
                output_dir=output_dir,
                version=version,
                node_bin=node_bin,
                uv=Path(uv),
                frontend_assets=(
                    frontend_assets
                    if (frontend_assets / "index.html").is_file()
                    else None
                ),
                dependency_wheels=(
                    dependency_wheels
                    if dependency_wheels is not None and dependency_wheels.is_dir()
                    else None
                ),
            )
            publish_seconds = time.monotonic() - publish_started

            manifest_path = output_dir / f"manifest-{version}.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            on_progress("verifying", "正在校验 TOS latest.json")
            self._verify_latest(manifest)
            total_seconds = time.monotonic() - total_started
            return BuildResult(
                version=str(manifest["version"]),
                gitSha=str(manifest["gitSha"]),
                sha256=str(manifest["sha256"]),
                size=int(manifest["size"]),
                createdAt=str(manifest["createdAt"]),
                timings={
                    "fetchSeconds": round(fetch_seconds, 3),
                    "toolBootstrapSeconds": round(tools_seconds, 3),
                    "buildPublishSeconds": round(publish_seconds, 3),
                    "totalSeconds": round(total_seconds, 3),
                },
            )

    def _prepare_dependency_wheels(
        self,
        source_root: Path,
        prepared_root: Path,
        workspace: Path,
        on_progress: ProgressCallback,
    ) -> Path | None:
        dependency_manifest = prepared_root / "dependencies.json"
        prepared_wheels = prepared_root / "wheels"
        if not dependency_manifest.is_file() and prepared_wheels.is_dir():
            return prepared_wheels
        if not dependency_manifest.is_file():
            dependency_manifest = workspace / "dependencies.json"
            self._write_dependency_manifest(source_root, dependency_manifest)
        if dependency_manifest.is_file():
            if self._dependency_store is None:
                raise RuntimeError("Studio dependency cache is not configured.")
            on_progress("preparing", "正在从 TOS 缓存恢复 Studio 依赖包")
            destination = workspace / "dependency-wheels"
            self._dependency_store.materialize(dependency_manifest, destination)
            return destination
        return None

    def _write_dependency_manifest(
        self,
        source_root: Path,
        destination: Path,
    ) -> None:
        script = source_root / "veadk" / "cli" / "studio_dependencies.py"
        if not script.is_file():
            raise RuntimeError("Studio dependency manifest generator is missing.")
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "veadk.cli.studio_dependencies",
                "--manifest-only",
                "--manifest",
                str(destination),
            ],
            cwd=source_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=30,
        )
        if completed.returncode != 0 or not destination.is_file():
            output = completed.stdout[-4000:].decode(errors="replace")
            raise RuntimeError(f"Could not generate dependency manifest: {output}")

    def _download_source(
        self,
        request: ReleaseRequest,
        workspace: Path,
        on_progress: ProgressCallback,
    ) -> Path:
        archive = workspace / "source.tar.gz"
        if request.source_key:
            if self._source_store is None:
                raise RuntimeError("Source staging is not configured.")
            expected_key = self._source_store.expected_key(request.request_id)
            if request.source_key != expected_key:
                raise ValueError("sourceKey does not belong to requestId")
            on_progress("fetching", "正在从 TOS 暂存区获取 GitHub 源码")
            reported_size = 0

            def report_progress(size: int) -> None:
                nonlocal reported_size
                if size - reported_size >= _SOURCE_DOWNLOAD_REPORT_BYTES:
                    on_progress(
                        "fetching",
                        f"已下载暂存源码 {size // (1024 * 1024)} MiB",
                    )
                    reported_size = size

            self._source_store.download_and_delete(
                request.source_key,
                archive,
                max_bytes=_MAX_SOURCE_ARCHIVE_BYTES,
                on_progress=report_progress,
            )
            on_progress("extracting", "暂存源码下载完成，正在解压")
            return self._extract_source(archive, workspace)

        cloned_source = self._clone_source(request, workspace, on_progress)
        if cloned_source is not None:
            return cloned_source

        last_error: OSError | tarfile.TarError | None = None
        for url in self._source_urls(request):
            try:
                self._download_source_archive(url, archive, on_progress)
                with tarfile.open(archive, "r:gz"):
                    pass
                last_error = None
                break
            except (OSError, tarfile.TarError) as error:
                last_error = error
                archive.unlink(missing_ok=True)
        if last_error is not None:
            raise last_error
        on_progress("extracting", "GitHub 源码下载完成，正在解压")
        return self._extract_source(archive, workspace)

    def _clone_source(
        self,
        request: ReleaseRequest,
        workspace: Path,
        on_progress: ProgressCallback,
    ) -> Path | None:
        git = shutil.which("git")
        if git is None:
            on_progress("fetching", "运行环境没有 Git，改用源码归档")
            return None

        for index, url in enumerate(self._source_clone_urls(request)):
            destination = workspace / f"source-clone-{index}"
            on_progress("fetching", "正在浅克隆 main 分支的构建文件")
            try:
                subprocess.run(
                    [
                        git,
                        "clone",
                        "--quiet",
                        "--depth",
                        "1",
                        "--single-branch",
                        "--branch",
                        "main",
                        "--filter=blob:none",
                        "--sparse",
                        url,
                        str(destination),
                    ],
                    check=True,
                    timeout=_GIT_CLONE_ATTEMPT_SECONDS,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                head = self._git_output(git, destination, "rev-parse", "HEAD")
                if head != request.git_sha:
                    on_progress("fetching", "main 已前进，正在获取发布请求的精确 SHA")
                    subprocess.run(
                        [
                            git,
                            "-C",
                            str(destination),
                            "fetch",
                            "--quiet",
                            "--depth",
                            "1",
                            "origin",
                            request.git_sha,
                        ],
                        check=True,
                        timeout=_GIT_CLONE_ATTEMPT_SECONDS,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                    )
                    subprocess.run(
                        [
                            git,
                            "-C",
                            str(destination),
                            "checkout",
                            "--quiet",
                            "--detach",
                            request.git_sha,
                        ],
                        check=True,
                        timeout=_GIT_CLONE_ATTEMPT_SECONDS,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                    )
                subprocess.run(
                    [
                        git,
                        "-C",
                        str(destination),
                        "sparse-checkout",
                        "set",
                        "--no-cone",
                        *_SPARSE_CHECKOUT_PATHS,
                    ],
                    check=True,
                    timeout=_GIT_CLONE_ATTEMPT_SECONDS,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                if self._git_output(git, destination, "rev-parse", "HEAD") != (
                    request.git_sha
                ):
                    raise RuntimeError("Sparse clone resolved an unexpected Git SHA.")
                if not (destination / "frontend" / "package.json").is_file():
                    raise RuntimeError(
                        "Sparse clone produced no frontend/package.json."
                    )
                on_progress("fetching", "main 分支构建文件拉取完成")
                return destination
            except (OSError, RuntimeError, subprocess.SubprocessError):
                shutil.rmtree(destination, ignore_errors=True)
        on_progress("fetching", "Git 浅克隆失败，改用源码归档")
        return None

    def _git_output(self, git: str, repository: Path, *arguments: str) -> str:
        completed = subprocess.run(
            [git, "-C", str(repository), *arguments],
            check=True,
            timeout=_GIT_CLONE_ATTEMPT_SECONDS,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return completed.stdout.strip().lower()

    def _source_clone_urls(self, request: ReleaseRequest) -> tuple[str, ...]:
        repository = request.repository
        return (
            f"https://github.com/{repository}.git",
            f"{_GITHUB_CLONE_MIRROR}/{repository}.git",
        )

    def _source_urls(self, request: ReleaseRequest) -> tuple[str, ...]:
        repository = request.repository
        git_sha = request.git_sha
        return (
            f"{_GITHUB_ARCHIVE_MIRROR}/{repository}/archive/{git_sha}.tar.gz",
            f"https://codeload.github.com/{repository}/tar.gz/{git_sha}",
        )

    def _download_source_archive(
        self,
        url: str,
        archive: Path,
        on_progress: ProgressCallback,
    ) -> None:
        http_request = urllib.request.Request(
            url,
            headers={"User-Agent": "veadk-studio-release-server"},
        )
        size = 0
        reported_size = 0
        download_started = time.monotonic()
        with (
            urllib.request.urlopen(http_request, timeout=30) as response,
            archive.open("wb") as output,
        ):
            while chunk := response.read(1024 * 1024):
                elapsed = time.monotonic() - download_started
                if elapsed > _SOURCE_DOWNLOAD_ATTEMPT_SECONDS:
                    raise TimeoutError("GitHub source download attempt timed out.")
                size += len(chunk)
                if size > _MAX_SOURCE_ARCHIVE_BYTES:
                    raise ValueError("GitHub source archive exceeds 200 MiB.")
                output.write(chunk)
                if size - reported_size >= _SOURCE_DOWNLOAD_REPORT_BYTES:
                    on_progress(
                        "fetching",
                        f"已下载 GitHub 源码 {size // (1024 * 1024)} MiB",
                    )
                    reported_size = size

    def _extract_source(self, archive: Path, workspace: Path) -> Path:
        extract_root = workspace / "source"
        extract_root.mkdir()
        with tarfile.open(archive, "r:gz") as source_archive:
            members = source_archive.getmembers()
            if not members or len(members) > _MAX_SOURCE_ARCHIVE_MEMBERS:
                raise ValueError("Source archive member count is invalid.")
            extracted_size = 0
            for member in members:
                if not (member.isfile() or member.isdir()):
                    raise ValueError("Source archive contains an unsupported entry.")
                extracted_size += member.size
                if extracted_size > _MAX_SOURCE_EXTRACTED_BYTES:
                    raise ValueError("Source archive expands beyond 1 GiB.")
            source_archive.extractall(extract_root, members=members, filter="data")
        roots = [path for path in extract_root.iterdir() if path.is_dir()]
        if len(roots) != 1 or not (roots[0] / "frontend" / "package.json").is_file():
            raise ValueError("GitHub archive is not a VeADK source checkout.")
        return roots[0]

    def _ensure_node(self) -> Path:
        npm = shutil.which("npm")
        node = shutil.which("node")
        if npm and node:
            return Path(node).parent
        machine = platform.machine().lower()
        architecture = {"aarch64": "arm64", "arm64": "arm64"}.get(
            machine, "x64" if machine in {"amd64", "x86_64"} else ""
        )
        if not architecture:
            raise RuntimeError(f"Unsupported Node architecture: {machine}")
        install_root = Path(tempfile.gettempdir()) / "studio-release-tools"
        node_root = install_root / f"node-v{_NODE_VERSION}-linux-{architecture}"
        node_bin = node_root / "bin"
        if (node_bin / "node").is_file() and (node_bin / "npm").is_file():
            return node_bin
        install_root.mkdir(parents=True, exist_ok=True)
        archive_name = f"node-v{_NODE_VERSION}-linux-{architecture}.tar.xz"
        archive_path = install_root / archive_name
        expected = _NODE_ARCHIVE_SHA256[architecture]
        bundled_archive = Path(__file__).with_name(archive_name)
        if bundled_archive.is_file():
            content = bundled_archive.read_bytes()
            if hashlib.sha256(content).hexdigest() != expected:
                raise ValueError("Bundled Node archive checksum does not match.")
        else:
            last_error: OSError | ValueError | None = None
            for url in self._node_download_urls(archive_name):
                try:
                    with urllib.request.urlopen(url, timeout=120) as response:
                        content = response.read(128 * 1024 * 1024 + 1)
                    if len(content) > 128 * 1024 * 1024:
                        raise ValueError("Downloaded Node archive exceeds 128 MiB.")
                    if hashlib.sha256(content).hexdigest() != expected:
                        raise ValueError(
                            "Downloaded Node archive checksum does not match."
                        )
                    break
                except (OSError, ValueError) as error:
                    last_error = error
            else:
                if last_error is None:
                    raise RuntimeError("Node has no download source.")
                raise last_error
        archive_path.write_bytes(content)
        with tarfile.open(archive_path, "r:xz") as node_archive:
            node_archive.extractall(install_root, filter="data")
        if not (node_bin / "npm").is_file():
            raise RuntimeError("Node installation produced no npm executable.")
        return node_bin

    def _node_download_urls(self, archive_name: str) -> tuple[str, ...]:
        return tuple(
            f"{base}/v{_NODE_VERSION}/{archive_name}"
            for base in _NODE_DOWNLOAD_BASE_URLS
        )

    def _run_publisher(
        self,
        *,
        request: ReleaseRequest,
        source_root: Path,
        output_dir: Path,
        version: str,
        node_bin: Path | None,
        uv: Path,
        frontend_assets: Path | None,
        dependency_wheels: Path | None,
    ) -> None:
        credentials = resolve_credentials()
        command = [
            sys.executable,
            str(Path(__file__).with_name("publisher.py")),
            "--source-root",
            str(source_root),
            "--output-dir",
            str(output_dir),
            "--version",
            version,
            "--git-sha",
            request.git_sha,
            "--bucket",
            self._settings.bucket,
            "--region",
            self._settings.region,
            "--prefix",
            self._settings.release_prefix,
        ]
        for item in request.changelog:
            command.extend(("--changelog", item))
        if frontend_assets is not None:
            command.extend(("--frontend-assets", str(frontend_assets)))
        if dependency_wheels is None:
            raise RuntimeError("Prepared Studio dependency wheels are missing.")
        command.extend(("--dependency-wheels", str(dependency_wheels)))
        env = os.environ.copy()
        env["NODE_OPTIONS"] = _node_options(
            env.get("NODE_OPTIONS", ""),
            _node_heap_limit_mb(),
        )
        path_entries = [str(uv.parent)]
        if node_bin is not None:
            path_entries.insert(0, str(node_bin))
        path_entries.append(env.get("PATH", ""))
        env.update(
            {
                "PATH": os.pathsep.join(path_entries),
                "VOLCENGINE_ACCESS_KEY": credentials.access_key,
                "VOLCENGINE_SECRET_KEY": credentials.secret_key,
                "VOLCENGINE_SESSION_TOKEN": credentials.session_token,
                "TZ": "Asia/Shanghai",
                "PIP_INDEX_URL": _PYPI_SIMPLE_INDEX,
                "UV_CACHE_DIR": str(
                    Path(tempfile.gettempdir()) / "studio-release-tools" / "uv-cache"
                ),
                "UV_DEFAULT_INDEX": _PYPI_SIMPLE_INDEX,
                "npm_config_cache": str(
                    Path(tempfile.gettempdir()) / "studio-release-tools" / "npm-cache"
                ),
                "npm_config_registry": _NPM_REGISTRY,
                "npm_config_replace_registry_host": "always",
            }
        )
        log_path = output_dir.parent / "publisher.log"
        with log_path.open("wb") as output:
            completed = subprocess.run(
                command,
                cwd=source_root,
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
                check=False,
            )
        if completed.returncode != 0:
            tail = log_path.read_bytes()[-8000:].decode(errors="replace")
            raise RuntimeError(
                f"Studio publisher exited with {completed.returncode}: {tail}"
            )

    def _verify_latest(self, expected: dict[str, object]) -> None:
        import tos

        credentials = resolve_credentials()
        client = tos.TosClientV2(
            credentials.access_key,
            credentials.secret_key,
            security_token=credentials.session_token or None,
            endpoint=f"tos-{self._settings.region}.volces.com",
            region=self._settings.region,
        )
        response = client.get_object(
            bucket=self._settings.bucket,
            key=f"{self._settings.release_prefix.strip().strip('/')}/latest.json",
        )
        content = bytearray()
        for chunk in response:
            if len(content) + len(chunk) > 64 * 1024:
                raise RuntimeError("Published latest.json is too large.")
            content.extend(chunk)
        actual = json.loads(content)
        for field in ("version", "gitSha", "sha256", "size"):
            if actual.get(field) != expected.get(field):
                raise RuntimeError(f"Published latest.json has mismatched {field}.")


__all__ = ["ProgressCallback", "ReleaseBuilder", "StudioReleaseBuilder"]
