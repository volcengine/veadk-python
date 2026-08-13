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

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from typing import Mapping, Sequence
import zipfile

from ..sandbox_remote import SandboxRemoteTransport


ARTIFACT_ROOT = "/home/gem/.vibe/task/artifacts"
ARTIFACT_FILENAME = "artifact.zip"
ARTIFACT_DESCRIPTOR_FILENAME = "descriptor.json"
ARTIFACT_WORKER_PATH = "/home/gem/.vibe/task/artifact-worker.py"
ARTIFACT_REQUEST_PATH = "/home/gem/.vibe/task/artifact-request.json"
MANIFEST_FILENAME = "artifact-manifest.json"
MAX_ARTIFACT_BYTES = 20 * 1024 * 1024
MAX_ARTIFACT_FILES = 2_000
MAX_SOURCE_FILE_BYTES = 5 * 1024 * 1024

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    rb"(?im)^\s*(?:export\s+)?(?:[A-Z0-9_]*(?:SECRET[_-]?ACCESS[_-]?KEY|PASSWORD|PASSWD|PRIVATE[_-]?KEY)[A-Z0-9_]*)\s*[:=]\s*[^\s#]{4,}"
)
_EXCLUDED_DIR_NAMES = frozenset(
    {
        ".cache",
        ".codex",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        ".vibe",
        "__pycache__",
        "cache",
        "caches",
        "node_modules",
        "secrets",
        "venv",
    }
)
_EXCLUDED_FILE_NAMES = frozenset({".env", ".env.local", ".env.production"})
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

# This worker is uploaded because production Sandboxes do not contain this package.
# Keep it dependency-free and self-contained; its request is host-authored, but every
# path and limit is still validated before filesystem access.
REMOTE_ARTIFACT_WORKER_SOURCE = r'''import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
import zipfile

ROOT = "/home/gem/.vibe/task/artifacts"
WORKSPACES = "/home/gem/workspace"
FILENAME = "artifact.zip"
DESCRIPTOR = "descriptor.json"
MANIFEST = "artifact-manifest.json"
MAX_BYTES = 20 * 1024 * 1024
MAX_FILES = 2000
MAX_FILE_BYTES = 5 * 1024 * 1024
EXCLUDED_DIRS = frozenset((".cache", ".codex", ".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", ".vibe", "__pycache__", "cache", "caches", "node_modules", "secrets", "venv"))
EXCLUDED_FILES = frozenset((".env", ".env.local", ".env.production"))
SENSITIVE = re.compile(rb"(?im)^\s*(?:export\s+)?(?:[A-Z0-9_]*(?:SECRET[_-]?ACCESS[_-]?KEY|PASSWORD|PASSWD|PRIVATE[_-]?KEY)[A-Z0-9_]*)\s*[:=]\s*[^\s#]{4,}")
HASH = re.compile(r"^[0-9a-f]{64}$")
TASK = re.compile(r"^vt-[0-9a-f]{12}-[0-9a-f]{24}$")
TIMESTAMP = (1980, 1, 1, 0, 0, 0)

def fail(message):
    raise ValueError(message)

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()

def excluded(relative, is_directory):
    if any(part in EXCLUDED_DIRS for part in relative.parts):
        return True
    name = relative.name
    return False if is_directory else name in EXCLUDED_FILES or name.startswith(".env.") or name.endswith(".log")

def collect(root):
    files = []
    total = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as error:
            raise ValueError("Project directory cannot be read") from error
        for entry in entries:
            relative_path = Path(entry.path).relative_to(root)
            relative = PurePosixPath(*relative_path.parts).as_posix()
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as error:
                raise ValueError("Project entry cannot be inspected: " + relative) from error
            if stat.S_ISLNK(metadata.st_mode):
                fail("Symlinks are not allowed: " + relative)
            is_directory = stat.S_ISDIR(metadata.st_mode)
            if excluded(relative_path, is_directory):
                continue
            if is_directory:
                pending.append(Path(entry.path))
                continue
            if not stat.S_ISREG(metadata.st_mode):
                fail("Non-regular files are not allowed: " + relative)
            if metadata.st_size > MAX_FILE_BYTES:
                fail("Project file exceeds the size limit: " + relative)
            try:
                Path(entry.path).resolve(strict=True).relative_to(root)
            except (OSError, ValueError) as error:
                raise ValueError("Project entry escapes its root: " + relative) from error
            if relative == MANIFEST:
                fail("Reserved artifact path is present: " + relative)
            files.append((relative, Path(entry.path), metadata.st_size))
            total += metadata.st_size
            if len(files) > MAX_FILES:
                fail("Project exceeds the file count limit")
            if total > MAX_BYTES:
                fail("Project exceeds the size limit")
    return sorted(files, key=lambda item: item[0])

def read_file(path, relative, expected_size):
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != expected_size:
            fail("Project file changed during packaging: " + relative)
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            content = stream.read(expected_size + 1)
        if len(content) != expected_size:
            fail("Project file changed during packaging: " + relative)
        return content
    except ValueError:
        raise
    except OSError as error:
        raise ValueError("Project file cannot be read safely: " + relative) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)

def write_member(archive, name, content):
    info = zipfile.ZipInfo(name, TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

def atomic_json(path, value):
    temporary = path.with_name("." + path.name + ".tmp")
    with open(temporary, "wb") as stream:
        stream.write(canonical(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)

def main():
    if len(sys.argv) != 2 or sys.argv[1] != "/home/gem/.vibe/task/artifact-request.json":
        fail("Artifact request path is invalid")
    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if set(request) != {"taskId", "manifest"}:
        fail("Artifact request has unexpected fields")
    task_id = request["taskId"]
    manifest = request["manifest"]
    if not isinstance(task_id, str) or TASK.fullmatch(task_id) is None:
        fail("Task identity is invalid")
    if set(manifest) != {"schemaVersion", "revision", "intentRevision", "evaluationPerformed", "hashes"}:
        fail("Artifact manifest has unexpected fields")
    hashes = manifest.get("hashes")
    if manifest.get("schemaVersion") != 1 or manifest.get("revision") != 1 or isinstance(manifest.get("intentRevision"), bool) or not isinstance(manifest.get("intentRevision"), int) or manifest["intentRevision"] < 0 or manifest.get("evaluationPerformed") is not False or not isinstance(hashes, dict) or set(hashes) != {"runtime", "status", "invoke", "log"} or any(not isinstance(value, str) or HASH.fullmatch(value) is None for value in hashes.values()):
        fail("Artifact manifest is invalid")
    root = Path(WORKSPACES) / task_id
    try:
        root = root.resolve(strict=True)
        root.relative_to(Path(WORKSPACES))
    except (OSError, ValueError) as error:
        raise ValueError("Project directory is unavailable") from error
    if not root.is_dir() or root != Path(WORKSPACES) / task_id:
        fail("Project path is invalid")
    captured = []
    total = 0
    for relative, path, expected_size in collect(root):
        content = read_file(path, relative, expected_size)
        if SENSITIVE.search(content):
            fail("Sensitive assignment found in project file: " + relative)
        captured.append((relative, content))
        total += len(content)
        if total > MAX_BYTES:
            fail("Project exceeds the size limit")
    output_dir = Path(ROOT) / "1"
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=output_dir, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                write_member(archive, MANIFEST, canonical(manifest) + b"\n")
                for relative, content in captured:
                    write_member(archive, relative, content)
            temporary.flush()
            os.fsync(temporary.fileno())
            size = temporary.tell()
        if size > MAX_BYTES:
            fail("Artifact exceeds the size limit")
        digest = hashlib.sha256(temporary_path.read_bytes()).hexdigest()
        final_path = output_dir / FILENAME
        os.replace(temporary_path, final_path)
        temporary_path = None
        descriptor = {"revision": 1, "path": str(final_path), "sha256": digest, "size": size}
        atomic_json(output_dir / DESCRIPTOR, descriptor)
        directory_fd = os.open(output_dir, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        print(json.dumps(descriptor, sort_keys=True, separators=(",", ":")))
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

if __name__ == "__main__":
    main()
'''


class ArtifactError(ValueError):
    """Artifact contract or package validation failed."""


@dataclass(frozen=True)
class ArtifactDescriptor:
    revision: int
    path: str
    sha256: str
    size: int

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "ArtifactDescriptor":
        if set(value) != {"revision", "path", "sha256", "size"}:
            raise ArtifactError("Artifact descriptor has unexpected fields")
        revision = value.get("revision")
        path = value.get("path")
        digest = value.get("sha256")
        size = value.get("size")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise ArtifactError("Artifact revision is invalid")
        if not isinstance(path, str) or path != artifact_path(revision):
            raise ArtifactError("Artifact path is invalid")
        if not isinstance(digest, str) or _HASH_RE.fullmatch(digest) is None:
            raise ArtifactError("Artifact digest is invalid")
        if isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= MAX_ARTIFACT_BYTES:
            raise ArtifactError("Artifact size is invalid")
        return cls(revision=revision, path=path, sha256=digest, size=size)

    def as_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "path": self.path,
            "sha256": self.sha256,
            "size": self.size,
        }


@dataclass(frozen=True)
class ArtifactManifest:
    revision: int
    intent_revision: int
    runtime_sha256: str
    status_sha256: str
    invoke_sha256: str
    log_sha256: str

    def as_dict(self) -> dict[str, object]:
        if self.revision < 1 or self.intent_revision < 0:
            raise ArtifactError("Artifact manifest revision is invalid")
        hashes = {
            "runtime": self.runtime_sha256,
            "status": self.status_sha256,
            "invoke": self.invoke_sha256,
            "log": self.log_sha256,
        }
        if any(_HASH_RE.fullmatch(value) is None for value in hashes.values()):
            raise ArtifactError("Artifact manifest hash is invalid")
        return {
            "schemaVersion": 1,
            "revision": self.revision,
            "intentRevision": self.intent_revision,
            "evaluationPerformed": False,
            "hashes": hashes,
        }


def artifact_path(revision: int) -> str:
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise ArtifactError("Artifact revision is invalid")
    return f"{ARTIFACT_ROOT}/{revision}/{ARTIFACT_FILENAME}"


def artifact_descriptor_path(revision: int) -> str:
    artifact_path(revision)
    return f"{ARTIFACT_ROOT}/{revision}/{ARTIFACT_DESCRIPTOR_FILENAME}"


def remote_artifact_request(task_id: str, manifest: ArtifactManifest) -> bytes:
    if re.fullmatch(r"vt-[0-9a-f]{12}-[0-9a-f]{24}", task_id) is None:
        raise ArtifactError("Task identity is invalid")
    return _canonical_json({"taskId": task_id, "manifest": manifest.as_dict()}) + b"\n"


def package_project(
    project_dir: str | Path,
    manifest: ArtifactManifest,
    *,
    secret_values: Sequence[str | bytes] = (),
    artifact_root: str | Path = ARTIFACT_ROOT,
    max_files: int = MAX_ARTIFACT_FILES,
    max_bytes: int = MAX_ARTIFACT_BYTES,
) -> ArtifactDescriptor:
    """Build a deterministic sandbox artifact and atomically publish it."""
    if max_files < 1 or max_bytes < 1:
        raise ArtifactError("Artifact limits must be positive")
    root = Path(project_dir)
    try:
        root_resolved = root.resolve(strict=True)
    except OSError as error:
        raise ArtifactError("Project directory is unavailable") from error
    if not root_resolved.is_dir():
        raise ArtifactError("Project path is not a directory")

    files = _collect_files(root_resolved, max_files=max_files, max_bytes=max_bytes)
    secrets = tuple(_secret_bytes(item) for item in secret_values if item)
    captured: list[tuple[str, bytes]] = []
    captured_bytes = 0
    for relative, path, expected_size in files:
        content = _read_verified_file(path, relative, expected_size)
        _scan_content(content, relative, secrets)
        captured.append((relative, content))
        captured_bytes += len(content)
        if captured_bytes > max_bytes:
            raise ArtifactError("Project exceeds the size limit")

    manifest_bytes = _canonical_json(manifest.as_dict()) + b"\n"
    output_dir = Path(artifact_root) / str(manifest.revision)
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    final_path = output_dir / ARTIFACT_FILENAME
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=output_dir, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            with zipfile.ZipFile(
                temporary,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            ) as archive:
                _write_member(archive, MANIFEST_FILENAME, manifest_bytes)
                for relative, content in captured:
                    _write_member(archive, relative, content)
            temporary.flush()
            os.fsync(temporary.fileno())
            size = temporary.tell()
        if size > max_bytes:
            raise ArtifactError("Artifact exceeds the size limit")
        content = temporary_path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        os.replace(temporary_path, final_path)
        temporary_path = None
        _fsync_directory(output_dir)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return ArtifactDescriptor(
        revision=manifest.revision,
        path=artifact_path(manifest.revision),
        sha256=digest,
        size=size,
    )


async def download_and_validate_artifact(
    transport: SandboxRemoteTransport,
    descriptor_value: Mapping[str, object] | ArtifactDescriptor,
) -> bytes:
    descriptor = (
        descriptor_value
        if isinstance(descriptor_value, ArtifactDescriptor)
        else ArtifactDescriptor.from_mapping(descriptor_value)
    )
    # Revalidate instances too; callers must not be able to bypass the wire contract.
    descriptor = ArtifactDescriptor.from_mapping(descriptor.as_dict())
    content = await transport.download(descriptor.path, max_bytes=descriptor.size)
    if len(content) != descriptor.size:
        raise ArtifactError("Artifact size does not match descriptor")
    if hashlib.sha256(content).hexdigest() != descriptor.sha256:
        raise ArtifactError("Artifact digest does not match descriptor")
    _validate_zip(content)
    return content


def _collect_files(
    root: Path, *, max_files: int, max_bytes: int
) -> list[tuple[str, Path, int]]:
    files: list[tuple[str, Path, int]] = []
    source_bytes = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as error:
            raise ArtifactError("Project directory cannot be read") from error
        for entry in entries:
            relative_path = Path(entry.path).relative_to(root)
            relative = PurePosixPath(*relative_path.parts).as_posix()
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as error:
                raise ArtifactError(f"Project entry cannot be inspected: {relative}") from error
            if stat.S_ISLNK(metadata.st_mode):
                raise ArtifactError(f"Symlinks are not allowed: {relative}")
            is_directory = stat.S_ISDIR(metadata.st_mode)
            if _excluded(relative_path, is_directory):
                continue
            if is_directory:
                pending.append(Path(entry.path))
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise ArtifactError(f"Non-regular files are not allowed: {relative}")
            if metadata.st_size > MAX_SOURCE_FILE_BYTES:
                raise ArtifactError(f"Project file exceeds the size limit: {relative}")
            try:
                Path(entry.path).resolve(strict=True).relative_to(root)
            except (OSError, ValueError) as error:
                raise ArtifactError(f"Project entry escapes its root: {relative}") from error
            if relative == MANIFEST_FILENAME:
                raise ArtifactError(f"Reserved artifact path is present: {relative}")
            files.append((relative, Path(entry.path), metadata.st_size))
            source_bytes += metadata.st_size
            if len(files) > max_files:
                raise ArtifactError("Project exceeds the file count limit")
            if source_bytes > max_bytes:
                raise ArtifactError("Project exceeds the size limit")
    return sorted(files, key=lambda item: item[0])


def _excluded(relative: Path, is_directory: bool) -> bool:
    name = relative.name
    if any(part in _EXCLUDED_DIR_NAMES for part in relative.parts):
        return True
    if is_directory:
        return False
    return name in _EXCLUDED_FILE_NAMES or name.startswith(".env.") or name.endswith(".log")


def _secret_bytes(value: str | bytes) -> bytes:
    if isinstance(value, str):
        return value.encode()
    if isinstance(value, bytes):
        return value
    raise TypeError("secret values must be strings or bytes")


def _read_verified_file(path: Path, relative: str, expected_size: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != expected_size:
                raise ArtifactError(f"Project file changed during packaging: {relative}")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                content = stream.read(expected_size + 1)
            if len(content) != expected_size:
                raise ArtifactError(f"Project file changed during packaging: {relative}")
            return content
        finally:
            os.close(descriptor)
    except ArtifactError:
        raise
    except OSError as error:
        raise ArtifactError(f"Project file cannot be read safely: {relative}") from error


def _scan_content(content: bytes, relative: str, secrets: Sequence[bytes]) -> None:
    if any(secret and secret in content for secret in secrets):
        raise ArtifactError(f"Supplied secret value found in project file: {relative}")
    if _SENSITIVE_ASSIGNMENT_RE.search(content):
        raise ArtifactError(f"Sensitive assignment found in project file: {relative}")


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def _write_member(archive: zipfile.ZipFile, name: str, content: bytes) -> None:
    info = zipfile.ZipInfo(name, _ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _validate_zip(content: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            if len(members) > MAX_ARTIFACT_FILES + 1:
                raise ArtifactError("Artifact exceeds the file count limit")
            names: set[str] = set()
            total_size = 0
            for member in members:
                path = PurePosixPath(member.filename)
                if (
                    not member.filename
                    or member.filename.startswith(("/", "\\"))
                    or "\\" in member.filename
                    or member.filename != path.as_posix()
                    or any(part in {"", ".", ".."} for part in path.parts)
                    or member.is_dir()
                    or member.filename in names
                ):
                    raise ArtifactError("Artifact contains an unsafe path")
                mode = member.external_attr >> 16
                file_type = stat.S_IFMT(mode)
                if file_type not in {0, stat.S_IFREG}:
                    raise ArtifactError("Artifact contains a non-regular entry")
                names.add(member.filename)
                total_size += member.file_size
                if member.file_size > MAX_SOURCE_FILE_BYTES or total_size > MAX_ARTIFACT_BYTES:
                    raise ArtifactError("Artifact expanded content exceeds the size limit")
                with archive.open(member) as source:
                    while source.read(64 * 1024):
                        pass
            if MANIFEST_FILENAME not in names:
                raise ArtifactError("Artifact manifest is missing")
    except (zipfile.BadZipFile, RuntimeError, OSError) as error:
        raise ArtifactError("Artifact is not a valid ZIP archive") from error
