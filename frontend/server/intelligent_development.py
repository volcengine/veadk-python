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

"""Credential and immutable-delivery primitives for intelligent development.

Codex owns intent handling, implementation, and validation.  This module has no
independent verifier or cloud Runtime controller.
"""

from __future__ import annotations

from dataclasses import dataclass
import json


RELEASE_ROOT = "/home/gem/.intelligent-development/releases"
CURRENT_POINTER = "/home/gem/.intelligent-development/published.json"


def release_path(artifact_sha256: str, validation_report_sha256: str) -> str:
    """Return the immutable directory for one source-and-evidence pair."""
    return f"{RELEASE_ROOT}/{artifact_sha256}-{validation_report_sha256}"


@dataclass(frozen=True)
class StudioCredentials:
    access_key_id: str
    secret_access_key: str
    session_token: str | None = None

    def __post_init__(self) -> None:
        if not self.access_key_id or not self.secret_access_key:
            raise ValueError("Studio credentials are incomplete")
        if any("\x00" in value for value in self.secret_values):
            raise ValueError("Studio credentials are invalid")

    @property
    def secret_values(self) -> tuple[str, ...]:
        return tuple(
            value
            for value in (
                self.access_key_id,
                self.secret_access_key,
                self.session_token,
            )
            if value
        )

    def as_remote_json(self) -> bytes:
        return json.dumps(
            {
                "accessKeyId": self.access_key_id,
                "secretAccessKey": self.secret_access_key,
                "sessionToken": self.session_token,
            },
            separators=(",", ":"),
        ).encode()


@dataclass(frozen=True)
class DeliveryReference:
    artifact_sha256: str
    artifact_size: int
    validation_report_sha256: str
    session_id: str
    agent_name: str
    entry_point: str
    file_count: int
    validated_at: str
    gate_summary: tuple[str, ...]
    verified: bool
    validation_summary: str

    def as_dict(self) -> dict[str, object]:
        return {
            "sessionId": self.session_id,
            "artifactSha256": self.artifact_sha256,
            "artifactSize": self.artifact_size,
            "validationReportSha256": self.validation_report_sha256,
            "agentName": self.agent_name,
            "entryPoint": self.entry_point,
            "fileCount": self.file_count,
            "validatedAt": self.validated_at,
            "gateSummary": list(self.gate_summary),
            "verified": self.verified,
            "validationSummary": self.validation_summary,
        }


REMOTE_DELIVERY_WORKER = r"""import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import zipfile

ROOT = Path("/home/gem/.intelligent-development")
WORKSPACES = Path("/home/gem/workspace")
RELEASES = ROOT / "releases"
CURRENT = ROOT / "published.json"
MAX_BYTES = 20 * 1024 * 1024
MAX_FILES = 2000
ZIP_TIME = (1980, 1, 1, 0, 0, 0)
EXCLUDED_NAMES = {".git", ".agentkit", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".DS_Store", "dist", "target"}
FORBIDDEN_DIRECTORIES = {".aws", ".ssh", ".kube"}
FORBIDDEN_FILE_NAMES = {"id_rsa", "id_ed25519"}
FORBIDDEN_SUFFIXES = {".key", ".pem", ".crt", ".secret", ".p12", ".pfx"}
COMPLETION_PREFIXES = (
    ".intelligent-development-result-",
    ".studio-intelligent-development-",
)

def fail(message):
    raise ValueError(message)

def atomic_json(path, value):
    fd, temporary = tempfile.mkstemp(prefix=".pointer-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)

def read_regular(path, expected_mode=None):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            fail("Delivery input is not a regular file")
        if expected_mode is not None and stat.S_IMODE(metadata.st_mode) != expected_mode:
            fail("Delivery secret mode is invalid")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            return stream.read(MAX_BYTES + 1)
    finally:
        os.close(descriptor)

def zip_member(archive, name, content):
    info = zipfile.ZipInfo(name, ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

def project_path(value):
    if not isinstance(value, str):
        fail("Delivery project is invalid")
    path = Path(value)
    try:
        workspace_root = WORKSPACES.resolve(strict=True)
        if path.parent != WORKSPACES or path.parent.resolve(strict=True) != workspace_root:
            fail("Delivery project is invalid")
        if path.resolve(strict=True) != path or not stat.S_ISDIR(os.lstat(path).st_mode):
            fail("Delivery project is invalid")
    except (OSError, ValueError) as error:
        raise ValueError("Delivery project is unavailable") from error
    return path

def collect_project(path, secrets):
    files = []
    total = 0
    for current, directories, names in os.walk(path, topdown=True, followlinks=False):
        current_path = Path(current)
        relative_root = current_path.relative_to(path)
        kept = []
        for name in sorted(directories):
            candidate = current_path / name
            metadata = os.lstat(candidate)
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                fail("Delivery source contains an unsafe entry")
            if name.lower() in FORBIDDEN_DIRECTORIES:
                fail("Delivery source contains a forbidden credential directory")
            if name not in EXCLUDED_NAMES:
                kept.append(name)
        directories[:] = kept
        for name in sorted(names):
            candidate = current_path / name
            relative = relative_root / name
            if name in EXCLUDED_NAMES or name.startswith(COMPLETION_PREFIXES):
                continue
            lower_name = name.lower()
            if lower_name == ".env" or (lower_name.startswith(".env.") and lower_name != ".env.example"):
                fail("Delivery source contains a forbidden local file")
            if lower_name in FORBIDDEN_FILE_NAMES or Path(lower_name).suffix in FORBIDDEN_SUFFIXES:
                fail("Delivery source contains a forbidden credential file")
            metadata = os.lstat(candidate)
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                fail("Delivery source contains an unsafe entry")
            content = read_regular(candidate)
            total += len(content)
            if total > MAX_BYTES:
                fail("Delivery expanded source exceeds the limit")
            if any(secret in content for secret in secrets):
                fail("Delivery source contains supplied credentials")
            files.append((relative.as_posix(), content))
            if len(files) > MAX_FILES:
                fail("Delivery source has too many files")
    if not files:
        fail("Delivery source is empty")
    return files

def main():
    if len(sys.argv) != 2:
        fail("Delivery request is invalid")
    request_path = Path(sys.argv[1])
    request = json.loads(read_regular(request_path).decode("utf-8"))
    if set(request) != {"projectRoot", "report", "secretPath", "agentName", "entryPoint", "manifestSha256"}:
        fail("Delivery request fields are invalid")
    project = project_path(request["projectRoot"])
    secret_path = Path(request["secretPath"])
    try:
        secrets_value = json.loads(read_regular(secret_path, 0o600).decode("utf-8"))
    finally:
        secret_path.unlink(missing_ok=True)
    if not isinstance(secrets_value, list) or any(not isinstance(value, str) for value in secrets_value):
        fail("Delivery secrets are invalid")
    secrets = tuple(value.encode() for value in secrets_value if value)
    files = collect_project(project, secrets)
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    RELEASES.mkdir(mode=0o700, parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".release-", dir=RELEASES))
    try:
        artifact = staging / "artifact.zip"
        with open(artifact, "w+b") as output:
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                for name, member_content in files:
                    zip_member(archive, name, member_content)
            output.flush()
            os.fsync(output.fileno())
            size = output.tell()
        if size > MAX_BYTES:
            fail("Delivery artifact exceeds the limit")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        report = dict(request["report"])
        report["artifactGate"] = True
        report["artifactSha256"] = digest
        agentkit_yaml = next((content for name, content in files if name == "agentkit.yaml"), b"")
        if hashlib.sha256(agentkit_yaml).hexdigest() != request["manifestSha256"]:
            fail("Delivery agentkit.yaml changed during packaging")
        agent_name = request["agentName"]
        entry_point = request["entryPoint"]
        if not isinstance(agent_name, str) or not agent_name.strip():
            fail("Delivery agent name is invalid")
        if not isinstance(entry_point, str) or entry_point not in {name for name, _ in files}:
            fail("Delivery entry point is invalid")
        report["agentName"] = agent_name.strip()
        report["entryPoint"] = entry_point
        report["fileCount"] = len(files)
        report_bytes = (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode()
        report_digest = hashlib.sha256(report_bytes).hexdigest()
        release = RELEASES / f"{digest}-{report_digest}"
        descriptor = {
            "sessionId": report.get("sessionId"),
            "artifactSha256": digest,
            "artifactSize": size,
            "agentName": agent_name.strip(),
            "entryPoint": entry_point,
            "fileCount": len(files),
            "artifactPath": str(release / "artifact.zip"),
            "descriptorPath": str(release / "descriptor.json"),
            "validationReportPath": str(release / "validation" / f"{report_digest}.json"),
            "validationReportSha256": report_digest,
            "releasePath": str(release),
        }
        descriptor_bytes = (json.dumps(descriptor, sort_keys=True, separators=(",", ":")) + "\n").encode()
        validation_dir = staging / "validation"
        validation_dir.mkdir(mode=0o700)
        (validation_dir / f"{report_digest}.json").write_bytes(report_bytes)
        (staging / "descriptor.json").write_bytes(descriptor_bytes)
        for child in (artifact, staging / "descriptor.json", validation_dir / f"{report_digest}.json"):
            with open(child, "rb") as stream:
                os.fsync(stream.fileno())
        if release.exists():
            if read_regular(release / "artifact.zip") != artifact.read_bytes() or read_regular(release / "descriptor.json") != descriptor_bytes or read_regular(release / "validation" / f"{report_digest}.json") != report_bytes:
                fail("Immutable release conflicts with existing content")
        else:
            os.rename(staging, release)
        atomic_json(CURRENT, {
            "artifactSha256": digest,
            "validationReportSha256": report_digest,
            "releasePath": str(release),
        })
        print(json.dumps(descriptor, sort_keys=True, separators=(",", ":")))
    finally:
        if staging.exists():
            for child in sorted(staging.rglob("*"), reverse=True):
                if child.is_dir():
                    child.rmdir()
                else:
                    child.unlink()
            staging.rmdir()

if __name__ == "__main__":
    main()
"""


__all__ = [
    "CURRENT_POINTER",
    "DeliveryReference",
    "RELEASE_ROOT",
    "REMOTE_DELIVERY_WORKER",
    "StudioCredentials",
    "release_path",
]
