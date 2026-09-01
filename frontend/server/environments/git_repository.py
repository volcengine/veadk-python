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

"""Safely inspect and snapshot public Git repositories for environment builds."""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import stat
import subprocess
import tempfile
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import SplitResult, urlsplit, urlunsplit

from .models import GitSource, RepositoryInspection

_REF_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,511}")
_DEFAULT_MAX_FILES = 20_000
_DEFAULT_MAX_BYTES = 200 * 1024 * 1024
_DEFAULT_TIMEOUT_SECONDS = 45


class GitRepositoryError(ValueError):
    """A repository cannot safely be inspected or used as a build source."""


@dataclass(frozen=True)
class RepositoryFile:
    path: str
    content: bytes
    mode: int = 0o644


@dataclass(frozen=True)
class RepositorySnapshot:
    inspection: RepositoryInspection
    files: tuple[RepositoryFile, ...]


@dataclass(frozen=True)
class _PinnedRepository:
    url: str
    curlopt_resolve: str


class GitRepositoryInspector(Protocol):
    def inspect(self, repository_url: str, ref: str = "") -> RepositoryInspection: ...

    def snapshot(self, source: GitSource) -> RepositorySnapshot: ...


class PublicGitRepositoryInspector:
    """Clone public HTTPS repositories with bounded resources and no redirects."""

    def __init__(
        self,
        *,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
        max_files: int = _DEFAULT_MAX_FILES,
        max_bytes: int = _DEFAULT_MAX_BYTES,
        resolver: Callable[..., Sequence[tuple]] = socket.getaddrinfo,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_files = max_files
        self.max_bytes = max_bytes
        self._resolver = resolver

    def inspect(self, repository_url: str, ref: str = "") -> RepositoryInspection:
        with tempfile.TemporaryDirectory(prefix="veadk-environment-git-") as tmp:
            root, inspection = self._checkout(repository_url, ref, Path(tmp))
            files = self._read_files(root, include_content=False)
            dockerfiles = _dockerfile_paths(file.path for file in files)
            return inspection.model_copy(update={"dockerfiles": dockerfiles})

    def snapshot(self, source: GitSource) -> RepositorySnapshot:
        with tempfile.TemporaryDirectory(prefix="veadk-environment-git-") as tmp:
            root, inspection = self._checkout(
                source.repository_url, source.ref, Path(tmp)
            )
            files = self._read_files(root, include_content=True)
            dockerfiles = _dockerfile_paths(file.path for file in files)
            if source.dockerfile_path not in dockerfiles:
                raise GitRepositoryError(
                    f"所选 Dockerfile 不存在：{source.dockerfile_path}"
                )
            return RepositorySnapshot(
                inspection=inspection.model_copy(update={"dockerfiles": dockerfiles}),
                files=tuple(files),
            )

    def _checkout(
        self, repository_url: str, ref: str, workspace: Path
    ) -> tuple[Path, RepositoryInspection]:
        repository = self._validate_url(repository_url)
        normalized_url = repository.url
        normalized_ref = self._validate_ref(ref)
        root = workspace / "repository"
        if normalized_ref:
            self._run_git(
                "init",
                "--quiet",
                str(root),
                cwd=workspace,
                curlopt_resolve=repository.curlopt_resolve,
            )
            self._run_git(
                "-C",
                str(root),
                "remote",
                "add",
                "origin",
                normalized_url,
                cwd=workspace,
                curlopt_resolve=repository.curlopt_resolve,
            )
            self._run_git(
                "-C",
                str(root),
                "fetch",
                "--quiet",
                "--depth=1",
                "--filter=blob:none",
                "--no-tags",
                "--no-recurse-submodules",
                "origin",
                normalized_ref,
                cwd=workspace,
                curlopt_resolve=repository.curlopt_resolve,
            )
            commit_ref = "FETCH_HEAD"
            self._validate_tree(
                root,
                commit_ref,
                workspace,
                curlopt_resolve=repository.curlopt_resolve,
            )
            self._run_git(
                "-C",
                str(root),
                "checkout",
                "--quiet",
                "--detach",
                "FETCH_HEAD",
                cwd=workspace,
                curlopt_resolve=repository.curlopt_resolve,
            )
            resolved_ref = normalized_ref
        else:
            self._run_git(
                "clone",
                "--quiet",
                "--depth=1",
                "--filter=blob:none",
                "--single-branch",
                "--no-tags",
                "--no-checkout",
                "--no-recurse-submodules",
                normalized_url,
                str(root),
                cwd=workspace,
                curlopt_resolve=repository.curlopt_resolve,
            )
            commit_ref = "HEAD"
            self._validate_tree(
                root,
                commit_ref,
                workspace,
                curlopt_resolve=repository.curlopt_resolve,
            )
            self._run_git(
                "-C",
                str(root),
                "checkout",
                "--quiet",
                cwd=workspace,
                curlopt_resolve=repository.curlopt_resolve,
            )
            resolved_ref = self._run_git(
                "-C",
                str(root),
                "branch",
                "--show-current",
                cwd=workspace,
                curlopt_resolve=repository.curlopt_resolve,
            ).strip()
        if (root / ".gitmodules").exists():
            raise GitRepositoryError("代码仓库包含 Git submodule，暂不支持构建。")
        commit_sha = self._run_git(
            "-C",
            str(root),
            "rev-parse",
            "HEAD",
            cwd=workspace,
            curlopt_resolve=repository.curlopt_resolve,
        ).strip()
        return root, RepositoryInspection(
            repositoryUrl=normalized_url,
            ref=resolved_ref or commit_sha,
            commitSha=commit_sha,
            dockerfiles=[],
        )

    def _validate_tree(
        self,
        root: Path,
        commit_ref: str,
        workspace: Path,
        *,
        curlopt_resolve: str,
    ) -> None:
        listing = self._run_git(
            "-C",
            str(root),
            "ls-tree",
            "-r",
            "-l",
            commit_ref,
            cwd=workspace,
            curlopt_resolve=curlopt_resolve,
        )
        file_count = 0
        total_bytes = 0
        for line in listing.splitlines():
            metadata, separator, _path = line.partition("\t")
            parts = metadata.split()
            if not separator or len(parts) != 4:
                raise GitRepositoryError("Git 仓库文件索引格式无效。")
            mode, kind, _object_id, raw_size = parts
            if mode == "160000" or kind == "commit":
                raise GitRepositoryError("代码仓库包含 Git submodule，暂不支持构建。")
            if mode == "120000":
                raise GitRepositoryError("代码仓库包含符号链接，暂不支持构建。")
            if kind != "blob":
                continue
            try:
                size = int(raw_size)
            except ValueError as error:
                raise GitRepositoryError("Git 仓库文件索引格式无效。") from error
            file_count += 1
            total_bytes += size
            if file_count > self.max_files:
                raise GitRepositoryError(f"代码仓库文件数不能超过 {self.max_files}。")
            if total_bytes > self.max_bytes:
                raise GitRepositoryError(
                    f"代码仓库大小不能超过 {self.max_bytes // (1024 * 1024)} MiB。"
                )

    def _validate_url(self, value: str) -> _PinnedRepository:
        raw = value.strip()
        parsed = urlsplit(raw)
        if parsed.scheme.casefold() != "https":
            raise GitRepositoryError("仅支持公开的 HTTPS Git 仓库地址。")
        if parsed.username is not None or parsed.password is not None:
            raise GitRepositoryError("Git 仓库地址不能包含用户名、密码或 Token。")
        if parsed.query or parsed.fragment:
            raise GitRepositoryError("Git 仓库地址不能包含查询参数或片段。")
        hostname = (parsed.hostname or "").strip().rstrip(".")
        if not hostname:
            raise GitRepositoryError("Git 仓库地址缺少有效域名。")
        try:
            port = parsed.port
        except ValueError as error:
            raise GitRepositoryError("Git 仓库地址端口无效。") from error
        if port not in {None, 443}:
            raise GitRepositoryError("公开 Git 仓库仅支持 HTTPS 标准端口。")
        normalized_host = hostname.encode("idna").decode("ascii").lower()
        addresses = self._require_public_host(normalized_host, port or 443)
        netloc = normalized_host if port is None else f"{normalized_host}:{port}"
        path = parsed.path.rstrip("/")
        if not path or path == "/":
            raise GitRepositoryError("Git 仓库地址缺少仓库路径。")
        pinned_addresses = ",".join(
            f"[{address}]" if ":" in address else address for address in addresses
        )
        return _PinnedRepository(
            url=urlunsplit(SplitResult("https", netloc, path, "", "")),
            curlopt_resolve=f"{normalized_host}:{port or 443}:{pinned_addresses}",
        )

    def _require_public_host(self, hostname: str, port: int) -> tuple[str, ...]:
        if hostname.casefold() == "localhost":
            raise GitRepositoryError("Git 仓库地址不能指向本机或私有网络。")
        try:
            addresses = self._resolver(hostname, port, type=socket.SOCK_STREAM)
        except OSError as error:
            raise GitRepositoryError("无法解析 Git 仓库域名。") from error
        if not addresses:
            raise GitRepositoryError("无法解析 Git 仓库域名。")
        pinned: list[str] = []
        for item in addresses:
            address = str(item[4][0]).split("%", 1)[0]
            try:
                ip = ipaddress.ip_address(address)
            except ValueError as error:
                raise GitRepositoryError("Git 仓库域名解析结果无效。") from error
            if not ip.is_global:
                raise GitRepositoryError("Git 仓库地址不能指向本机或私有网络。")
            normalized = ip.compressed
            if normalized not in pinned:
                pinned.append(normalized)
        return tuple(pinned)

    @staticmethod
    def _validate_ref(value: str) -> str:
        ref = value.strip()
        if not ref:
            return ""
        if (
            not _REF_RE.fullmatch(ref)
            or ref.startswith(("-", "/"))
            or ref.endswith((".", "/"))
            or ".." in ref
            or "@{" in ref
            or "//" in ref
        ):
            raise GitRepositoryError("Git ref 格式无效。")
        return ref

    def _run_git(
        self,
        *args: str,
        cwd: Path,
        curlopt_resolve: str = "",
    ) -> str:
        command = [
            "git",
            "-c",
            "http.followRedirects=false",
            "-c",
            "protocol.file.allow=never",
            "-c",
            "protocol.ext.allow=never",
        ]
        if curlopt_resolve:
            command.extend(("-c", f"http.curloptResolve={curlopt_resolve}"))
        command.extend(args)
        environment = {
            **os.environ,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "",
            "GIT_SSH_COMMAND": "false",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        }
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=environment,
                capture_output=True,
                text=True,
                check=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            raise GitRepositoryError("探查 Git 仓库超时。") from error
        except (OSError, subprocess.CalledProcessError) as error:
            raise GitRepositoryError("无法读取公开 Git 仓库或指定 ref。") from error
        return result.stdout

    def _read_files(self, root: Path, *, include_content: bool) -> list[RepositoryFile]:
        result: list[RepositoryFile] = []
        total_bytes = 0
        for current, directories, names in os.walk(root, followlinks=False):
            directories[:] = sorted(name for name in directories if name != ".git")
            current_path = Path(current)
            for directory in directories:
                if (current_path / directory).is_symlink():
                    raise GitRepositoryError("代码仓库包含符号链接，暂不支持构建。")
            for name in sorted(names):
                path = current_path / name
                if path.is_symlink():
                    raise GitRepositoryError("代码仓库包含符号链接，暂不支持构建。")
                info = path.stat()
                if not stat.S_ISREG(info.st_mode):
                    raise GitRepositoryError("代码仓库包含不支持的特殊文件。")
                total_bytes += info.st_size
                if len(result) >= self.max_files:
                    raise GitRepositoryError(
                        f"代码仓库文件数不能超过 {self.max_files}。"
                    )
                if total_bytes > self.max_bytes:
                    raise GitRepositoryError(
                        f"代码仓库大小不能超过 {self.max_bytes // (1024 * 1024)} MiB。"
                    )
                relative = path.relative_to(root).as_posix()
                result.append(
                    RepositoryFile(
                        path=relative,
                        content=path.read_bytes() if include_content else b"",
                        mode=0o755 if info.st_mode & stat.S_IXUSR else 0o644,
                    )
                )
        return result


def _dockerfile_paths(paths: Iterable[str]) -> list[str]:
    candidates: list[str] = []
    for path in paths:
        name = path.rsplit("/", 1)[-1]
        if (
            name == "Dockerfile"
            or name.startswith("Dockerfile.")
            or name.endswith(".Dockerfile")
        ):
            candidates.append(path)
    return sorted(candidates, key=lambda item: (item.count("/"), item.casefold(), item))


__all__ = [
    "GitRepositoryError",
    "GitRepositoryInspector",
    "PublicGitRepositoryInspector",
    "RepositoryFile",
    "RepositorySnapshot",
]
