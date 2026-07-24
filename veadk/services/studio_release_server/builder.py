"""Fetch an exact GitHub revision and publish its Studio release."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
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

from veadk.services.studio_release_server.models import (
    BuildResult,
    ReleaseRequest,
    ReleaseServerSettings,
)
from veadk.services.studio_release_server.tos_store import (
    SourceStore,
    resolve_credentials,
)

_MAX_SOURCE_ARCHIVE_BYTES = 200 * 1024 * 1024
_SOURCE_DOWNLOAD_REPORT_BYTES = 8 * 1024 * 1024
_SOURCE_DOWNLOAD_TIMEOUT_SECONDS = 10 * 60
_NODE_VERSION = "22.17.0"
_NODE_ARCHIVE_SHA256 = {
    "arm64": "140aee84be6774f5fb3f404be72adbe8420b523f824de82daeb5ab218dab7b18",
    "x64": "325c0f1261e0c61bcae369a1274028e9cfb7ab7949c05512c5b1e630f7e80e12",
}

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str], None]


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
    ) -> None:
        self._settings = settings
        self._source_store = source_store

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

            tools_started = time.monotonic()
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

        url = (
            f"https://codeload.github.com/{request.repository}/tar.gz/{request.git_sha}"
        )
        http_request = urllib.request.Request(
            url,
            headers={"User-Agent": "veadk-studio-release-server"},
        )
        size = 0
        reported_size = 0
        download_started = time.monotonic()
        with urllib.request.urlopen(http_request, timeout=120) as response:
            with archive.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    if (
                        time.monotonic() - download_started
                        > _SOURCE_DOWNLOAD_TIMEOUT_SECONDS
                    ):
                        raise TimeoutError(
                            "GitHub source download exceeded 10 minutes."
                        )
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
        on_progress("extracting", "GitHub 源码下载完成，正在解压")
        return self._extract_source(archive, workspace)

    def _extract_source(self, archive: Path, workspace: Path) -> Path:
        extract_root = workspace / "source"
        extract_root.mkdir()
        with tarfile.open(archive, "r:gz") as source_archive:
            source_archive.extractall(extract_root, filter="data")
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
        url = f"https://nodejs.org/dist/v{_NODE_VERSION}/{archive_name}"
        with urllib.request.urlopen(url, timeout=120) as response:
            content = response.read()
        expected = _NODE_ARCHIVE_SHA256[architecture]
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("Downloaded Node archive checksum does not match.")
        archive_path.write_bytes(content)
        with tarfile.open(archive_path, "r:xz") as node_archive:
            node_archive.extractall(install_root, filter="data")
        if not (node_bin / "npm").is_file():
            raise RuntimeError("Node installation produced no npm executable.")
        return node_bin

    def _run_publisher(
        self,
        *,
        request: ReleaseRequest,
        source_root: Path,
        output_dir: Path,
        version: str,
        node_bin: Path,
        uv: Path,
    ) -> None:
        credentials = resolve_credentials()
        command = [
            sys.executable,
            "-m",
            "veadk.cli.studio_release",
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
        env = os.environ.copy()
        env.update(
            {
                "PATH": os.pathsep.join(
                    (str(node_bin), str(uv.parent), env.get("PATH", ""))
                ),
                "PYTHONPATH": os.pathsep.join(
                    (str(source_root), env.get("PYTHONPATH", ""))
                ),
                "VOLCENGINE_ACCESS_KEY": credentials.access_key,
                "VOLCENGINE_SECRET_KEY": credentials.secret_key,
                "VOLCENGINE_SESSION_TOKEN": credentials.session_token,
                "TZ": "Asia/Shanghai",
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
        actual = json.loads(b"".join(response))
        for field in ("version", "gitSha", "sha256", "size"):
            if actual.get(field) != expected.get(field):
                raise RuntimeError(f"Published latest.json has mismatched {field}.")


__all__ = ["ProgressCallback", "ReleaseBuilder", "StudioReleaseBuilder"]
