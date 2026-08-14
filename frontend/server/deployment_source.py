# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Validate and materialize AgentKit deployment source packages."""

from __future__ import annotations

import ast
import hashlib
import io
import re
import stat
import tokenize
import zipfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

import yaml

_DEFAULT_ENTRY_POINT = "app.py"
_MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
_MAX_ARCHIVE_FILES = 20_000
_MAX_EXPANDED_BYTES = 512 * 1024 * 1024
_MAX_FILE_BYTES = 128 * 1024 * 1024
_MAX_PATH_BYTES = 4 * 1024
_MAX_PATH_DEPTH = 64
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_AGENT_VARIABLE_NAMES = frozenset({"agent", "root_agent"})
_AGENT_RUNTIME_METHODS = frozenset({"run", "run_async"})


class DeploymentSourceError(ValueError):
    """Deployment source does not satisfy the trusted package contract."""


def _relative_path(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise DeploymentSourceError(f"{field} 必须是相对文件路径。")
    path = PurePosixPath(value)
    normalized = path.as_posix()
    if (
        not value
        or value.endswith("/")
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or value != normalized
        or path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
        or len(path.parts) > _MAX_PATH_DEPTH
        or len(normalized.encode("utf-8")) > _MAX_PATH_BYTES
    ):
        raise DeploymentSourceError(f"{field} 不是安全的相对文件路径：{value}")
    return normalized


def _target(base: Path, relative: str) -> Path:
    target = (base / relative).resolve()
    if not target.is_relative_to(base.resolve()):
        raise DeploymentSourceError(f"部署文件路径越界：{relative}")
    return target


def _is_macos_metadata(relative: str) -> bool:
    path = PurePosixPath(relative)
    return (
        path.parts[0] == "__MACOSX"
        or path.name == ".DS_Store"
        or path.name.startswith("._")
    )


def _configured_entry_point(base: Path) -> str:
    manifest_path = base / "agentkit.yaml"
    if not manifest_path.is_file():
        return _DEFAULT_ENTRY_POINT
    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise DeploymentSourceError(f"agentkit.yaml 无法解析：{error}") from error
    if manifest is None:
        return _DEFAULT_ENTRY_POINT
    if not isinstance(manifest, Mapping):
        raise DeploymentSourceError("agentkit.yaml 根节点必须是对象。")
    common = manifest.get("common")
    if common is None:
        return _DEFAULT_ENTRY_POINT
    if not isinstance(common, Mapping):
        raise DeploymentSourceError("agentkit.yaml 的 common 必须是对象。")
    value = common.get("entry_point")
    if value is None:
        return _DEFAULT_ENTRY_POINT
    return _relative_path(value, field="agentkit.yaml common.entry_point")


def _require_entry_point(base: Path, entry_point: str) -> str:
    target = _target(base, entry_point)
    if not target.is_file() or target.is_symlink():
        raise DeploymentSourceError(f"部署入口文件不存在：{entry_point}")
    return entry_point


def _reject_path_collisions(paths: set[str]) -> None:
    for relative in paths:
        path = PurePosixPath(relative)
        for parent in path.parents:
            if parent == PurePosixPath("."):
                break
            if parent.as_posix() in paths:
                raise DeploymentSourceError(
                    f"部署文件存在文件与目录路径冲突：{parent.as_posix()}"
                )


def _assigned_targets(node: ast.AST) -> list[ast.AST]:
    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return [target for item in targets for target in ast.walk(item)]
    return []


def _replaces_agent_runtime_method(node: ast.AST) -> bool:
    for target in _assigned_targets(node):
        if (
            isinstance(target, ast.Attribute)
            and target.attr in _AGENT_RUNTIME_METHODS
            and isinstance(target.value, ast.Name)
            and target.value.id in _AGENT_VARIABLE_NAMES
        ):
            return True
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "setattr"
        and len(node.args) >= 2
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id in _AGENT_VARIABLE_NAMES
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value in _AGENT_RUNTIME_METHODS
    )


def _validate_migration_python_contract(base: Path, paths: set[str]) -> None:
    for relative in sorted(path for path in paths if path.endswith(".py")):
        target = _target(base, relative)
        try:
            with tokenize.open(target) as source:
                tree = ast.parse(source.read(), filename=relative)
        except (OSError, SyntaxError, UnicodeError) as error:
            raise DeploymentSourceError(
                f"迁移产物中的 Python 文件无法解析：{relative}"
            ) from error
        if any(_replaces_agent_runtime_method(node) for node in ast.walk(tree)):
            raise DeploymentSourceError(
                "迁移产物修改了 Agent 的运行方法，无法保证 Runtime 调用兼容性："
                f"{relative}"
            )


def write_inline_source(base: Path, files: object) -> str:
    """Write browser-provided text files and resolve a compatible entry point."""
    if not isinstance(files, list) or not files:
        raise DeploymentSourceError("No files provided")
    seen: set[str] = set()
    validated: list[tuple[str, str]] = []
    for item in files:
        if not isinstance(item, Mapping):
            raise DeploymentSourceError("部署文件格式无效。")
        relative = _relative_path(item.get("path"), field="部署文件路径")
        if relative in seen:
            raise DeploymentSourceError(f"部署文件重复：{relative}")
        seen.add(relative)
        content = item.get("content")
        if not isinstance(content, str):
            raise DeploymentSourceError(f"部署文件内容必须是文本：{relative}")
        validated.append((relative, content))
    _reject_path_collisions(seen)
    for relative, content in validated:
        target = _target(base, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return _require_entry_point(base, _configured_entry_point(base))


def _manifest_files(manifest: object) -> tuple[dict[str, tuple[int, str]], str]:
    if not isinstance(manifest, Mapping):
        raise DeploymentSourceError("迁移产物清单格式无效。")
    files = manifest.get("files")
    startup = manifest.get("startup")
    if (
        not isinstance(files, list)
        or not files
        or len(files) > _MAX_ARCHIVE_FILES
        or not isinstance(startup, Mapping)
    ):
        raise DeploymentSourceError("迁移产物文件清单格式无效。")
    descriptors: dict[str, tuple[int, str]] = {}
    expanded_bytes = 0
    for item in files:
        if not isinstance(item, Mapping):
            raise DeploymentSourceError("迁移产物文件清单格式无效。")
        relative = _relative_path(item.get("path"), field="迁移产物路径")
        size = item.get("size")
        digest = item.get("sha256")
        if (
            relative in descriptors
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
            or size > _MAX_FILE_BYTES
            or not isinstance(digest, str)
            or not _SHA256_RE.fullmatch(digest)
        ):
            raise DeploymentSourceError("迁移产物文件清单格式无效。")
        expanded_bytes += size
        if expanded_bytes > _MAX_EXPANDED_BYTES:
            raise DeploymentSourceError("迁移产物解压后超过 512 MiB。")
        descriptors[relative] = (size, digest)
    _reject_path_collisions(set(descriptors))
    entry_point = _relative_path(
        startup.get("module"),
        field="迁移产物 startup.module",
    )
    if entry_point not in descriptors:
        raise DeploymentSourceError("迁移产物启动文件不在文件清单中。")
    return descriptors, entry_point


def extract_migration_source(
    base: Path,
    archive_content: bytes,
    manifest: object,
) -> str:
    """Verify every migration ZIP entry against its manifest before writing."""
    if not archive_content or len(archive_content) > _MAX_ARCHIVE_BYTES:
        raise DeploymentSourceError("迁移产物 ZIP 大小无效。")
    descriptors, entry_point = _manifest_files(manifest)
    seen: set[str] = set()
    materialized: set[str] = set()
    try:
        with zipfile.ZipFile(io.BytesIO(archive_content)) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if len(infos) != len(descriptors):
                raise DeploymentSourceError("迁移产物 ZIP 与文件清单不一致。")
            for info in infos:
                relative = _relative_path(info.filename, field="迁移产物 ZIP 路径")
                mode = info.external_attr >> 16
                if (
                    relative in seen
                    or info.flag_bits & 0x1
                    or stat.S_IFMT(mode) == stat.S_IFLNK
                ):
                    raise DeploymentSourceError("迁移产物 ZIP 包含不安全文件。")
                seen.add(relative)
                descriptor = descriptors.get(relative)
                if descriptor is None or info.file_size != descriptor[0]:
                    raise DeploymentSourceError("迁移产物 ZIP 与文件清单不一致。")
                content = archive.read(info)
                if hashlib.sha256(content).hexdigest() != descriptor[1]:
                    raise DeploymentSourceError("迁移产物文件完整性校验失败。")
                if _is_macos_metadata(relative):
                    continue
                target = _target(base, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                materialized.add(relative)
    except zipfile.BadZipFile as error:
        raise DeploymentSourceError("迁移产物 ZIP 格式无效。") from error
    entry_point = _require_entry_point(base, entry_point)
    _validate_migration_python_contract(base, materialized)
    return entry_point


__all__ = [
    "DeploymentSourceError",
    "extract_migration_source",
    "write_inline_source",
]
