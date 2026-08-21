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

"""Stage VeADK's public Sidecar integration in a managed build snapshot."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path


_REQUIREMENT_NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")
_REMOVED_DISTRIBUTIONS = {
    "agentkit-sdk-python",
    "agentkit-harness-sidecar-integration",
    "veadk-python",
}
_MANAGED_SDK_REQUIREMENT = "agentkit-sdk-python==0.8.4"
_IGNORED_PARTS = {".git", "__pycache__", "webui"}
_IGNORED_SUFFIXES = {".pyc", ".pyo"}
_BLOCKED_SUFFIXES = {".key", ".p12", ".pem", ".pfx"}
_REQUIRED_SOURCE_FILES = (
    "__init__.py",
    "extensions/harness/__init__.py",
    "extensions/harness/sidecar.py",
    "extensions/harness/sidecar_runtime/sidecar.py",
    "integrations/agentkit/app.py",
)
_MAX_SOURCE_FILE_BYTES = 8 * 1024 * 1024
_MAX_SOURCE_TOTAL_BYTES = 16 * 1024 * 1024


class ManagedSidecarSourceError(RuntimeError):
    """The managed source snapshot cannot be constructed safely."""


@dataclass(frozen=True)
class ManagedSidecarSourceSnapshot:
    file_count: int
    total_bytes: int


def _canonical_requirement_name(line: str) -> str | None:
    normalized = line.strip()
    if not normalized or normalized.startswith(("#", "-")):
        return None
    match = _REQUIREMENT_NAME_RE.match(normalized)
    if match is None:
        return None
    return match.group(1).lower().replace("_", "-").replace(".", "-")


def rewrite_managed_sidecar_requirements(requirements: str) -> str:
    """Use in-snapshot VeADK and install the approved public SDK explicitly."""

    lines: list[str] = []
    veadk_removed = False
    for line in requirements.splitlines():
        name = _canonical_requirement_name(line)
        if name in _REMOVED_DISTRIBUTIONS:
            veadk_removed = veadk_removed or name == "veadk-python"
            continue
        lines.append(line)
    if not veadk_removed:
        raise ManagedSidecarSourceError("veadk_requirement_missing")
    lines.insert(
        0,
        _MANAGED_SDK_REQUIREMENT,
    )
    lines.insert(
        0,
        "# veadk-python is provided by the Studio-managed public source snapshot.",
    )
    return "\n".join(lines).rstrip() + "\n"


def _source_files(package_dir: Path) -> list[tuple[Path, Path, int]]:
    files: list[tuple[Path, Path, int]] = []
    total_bytes = 0
    for source in sorted(package_dir.rglob("*")):
        relative = source.relative_to(package_dir)
        if any(
            part in _IGNORED_PARTS or part.startswith(".env") for part in relative.parts
        ):
            continue
        if source.is_symlink():
            raise ManagedSidecarSourceError("source_symlink_forbidden")
        if not source.is_file() or source.suffix.lower() in _IGNORED_SUFFIXES:
            continue
        if source.suffix.lower() in _BLOCKED_SUFFIXES:
            raise ManagedSidecarSourceError("sensitive_source_type_forbidden")
        size = source.stat().st_size
        if size > _MAX_SOURCE_FILE_BYTES:
            raise ManagedSidecarSourceError("source_file_too_large")
        total_bytes += size
        if total_bytes > _MAX_SOURCE_TOTAL_BYTES:
            raise ManagedSidecarSourceError("source_snapshot_too_large")
        files.append((source, relative, size))
    return files


def stage_managed_sidecar_veadk_source(
    project_dir: Path,
    *,
    package_dir: Path | None = None,
) -> ManagedSidecarSourceSnapshot:
    """Copy public VeADK runtime source into one ephemeral deployment tree."""

    project_dir = project_dir.resolve()
    source_root = (package_dir or Path(__file__).resolve().parents[1]).resolve()
    if source_root.name != "veadk" or any(
        not (source_root / relative).is_file() for relative in _REQUIRED_SOURCE_FILES
    ):
        raise ManagedSidecarSourceError("managed_source_incomplete")

    requirements_path = project_dir / "requirements.txt"
    if not requirements_path.is_file():
        raise ManagedSidecarSourceError("requirements_missing")
    target_root = project_dir / "veadk"
    if target_root.exists():
        raise ManagedSidecarSourceError("managed_source_target_exists")

    rewritten = rewrite_managed_sidecar_requirements(
        requirements_path.read_text(encoding="utf-8")
    )
    files = _source_files(source_root)

    target_root.mkdir(mode=0o755)
    for source, relative, _size in files:
        target = target_root / relative
        target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(source.stat().st_mode & 0o777)
    requirements_path.write_text(rewritten, encoding="utf-8")
    return ManagedSidecarSourceSnapshot(
        file_count=len(files),
        total_bytes=sum(size for _source, _relative, size in files),
    )
