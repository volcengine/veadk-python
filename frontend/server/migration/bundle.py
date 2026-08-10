# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

"""Integrity-checked AgentKit migration Runner assets bundled with Studio."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import tarfile
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, Protocol

_MANIFEST_NAME = "bundle-manifest.json"
_RUNNER_NAME = "runner.mjs"
_SKILLS_DIR = "skills"
_ARCHIVE_ROOT = "agentkit-migration-runtime"
_MAX_BUNDLE_BYTES = 8 * 1024 * 1024
_EXPECTED_FRAMEWORKS = (
    "langchain",
    "langgraph",
    "adk",
    "strands",
    "agentcore",
    "dify",
    "any",
)
_EXPECTED_PHASES = (
    "detecting",
    "planning",
    "migrating",
    "validating",
    "packaging",
)


class _Resource(Protocol):
    @property
    def name(self) -> str: ...

    def is_dir(self) -> bool: ...

    def is_file(self) -> bool: ...

    def iterdir(self) -> Any: ...

    def joinpath(self, *descendants: str) -> _Resource: ...

    def read_bytes(self) -> bytes: ...


class MigrationBundleError(RuntimeError):
    """The packaged Runner cannot be trusted or executed."""


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MigrationBundleError(f"Migration bundle {field} is invalid.")
    return value.strip()


def _string_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise MigrationBundleError(f"Migration bundle {field} is invalid.")
    normalized = tuple(_string(item, f"{field} item") for item in value)
    if len(set(normalized)) != len(normalized):
        raise MigrationBundleError(f"Migration bundle {field} contains duplicates.")
    return normalized


def _walk_files(root: _Resource, prefix: str = "") -> list[tuple[str, bytes]]:
    result: list[tuple[str, bytes]] = []
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        relative = f"{prefix}/{child.name}" if prefix else child.name
        if child.is_dir():
            result.extend(_walk_files(child, relative))
        elif child.is_file():
            result.append((relative, child.read_bytes()))
        else:
            raise MigrationBundleError(
                f"Migration bundle contains unsupported entry: {relative}."
            )
    return result


def _skills_digest(skill_files: tuple[tuple[str, bytes], ...]) -> str:
    digest = hashlib.sha256()
    for relative, content in skill_files:
        digest.update(f"{_sha256(content)}  ./{relative}\n".encode())
    return digest.hexdigest()


@dataclass(frozen=True)
class MigrationRunnerBundle:
    """Verified immutable files uploaded into one Studio-created Dev Session."""

    agentkit_cli_version: str
    source_commit: str
    capabilities: dict[str, object]
    manifest_bytes: bytes
    runner_bytes: bytes
    skill_files: tuple[tuple[str, bytes], ...]

    @classmethod
    def load(cls, root: Path | None = None) -> MigrationRunnerBundle:
        resource: _Resource
        if root is None:
            resource = files("veadk").joinpath("assets", "migration")
        else:
            resource = root
        try:
            manifest_bytes = resource.joinpath(_MANIFEST_NAME).read_bytes()
            runner_bytes = resource.joinpath(_RUNNER_NAME).read_bytes()
            skill_files = tuple(_walk_files(resource.joinpath(_SKILLS_DIR)))
        except (FileNotFoundError, OSError) as error:
            raise MigrationBundleError(
                "Studio migration Runner assets are missing."
            ) from error

        if (
            len(manifest_bytes)
            + len(runner_bytes)
            + sum(len(content) for _, content in skill_files)
            > _MAX_BUNDLE_BYTES
        ):
            raise MigrationBundleError("Studio migration Runner bundle is too large.")
        try:
            manifest = json.loads(manifest_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise MigrationBundleError(
                "Studio migration Runner manifest is invalid."
            ) from error
        if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
            raise MigrationBundleError(
                "Studio migration Runner manifest schema is unsupported."
            )

        runner_sha256 = _string(manifest.get("runner_sha256"), "runner_sha256")
        if _sha256(runner_bytes) != runner_sha256:
            raise MigrationBundleError(
                "Studio migration Runner checksum does not match its manifest."
            )
        skills_sha256 = _string(manifest.get("skills_sha256"), "skills_sha256")
        if _skills_digest(skill_files) != skills_sha256:
            raise MigrationBundleError(
                "Studio migration skill checksum does not match its manifest."
            )
        present_skills = {path for path, _ in skill_files}
        required_skills = _string_list(
            manifest.get("required_skill_files"),
            "required_skill_files",
        )
        missing_skills = sorted(set(required_skills) - present_skills)
        if missing_skills:
            raise MigrationBundleError(
                "Studio migration bundle is missing required skills: "
                + ", ".join(missing_skills)
            )

        capabilities = manifest.get("capabilities")
        if not isinstance(capabilities, dict):
            raise MigrationBundleError(
                "Studio migration Runner capabilities are invalid."
            )
        version = _string(manifest.get("agentkit_cli_version"), "version")
        if (
            capabilities.get("schema_version") != 1
            or capabilities.get("runner_version") != version
            or tuple(capabilities.get("frameworks") or ()) != _EXPECTED_FRAMEWORKS
            or tuple(capabilities.get("phases") or ()) != _EXPECTED_PHASES
            or capabilities.get("event_protocol") != "ndjson"
            or capabilities.get("manifest") != "migration-result.json"
        ):
            raise MigrationBundleError(
                "Studio migration Runner capabilities do not match Studio."
            )
        return cls(
            agentkit_cli_version=version,
            source_commit=_string(manifest.get("source_commit"), "source_commit"),
            capabilities=capabilities,
            manifest_bytes=manifest_bytes,
            runner_bytes=runner_bytes,
            skill_files=skill_files,
        )

    def archive(self) -> bytes:
        """Build a deterministic archive for upload to a Dev Sandbox Session."""
        target = io.BytesIO()
        with gzip.GzipFile(fileobj=target, mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                self._add_file(
                    archive,
                    f"{_ARCHIVE_ROOT}/{_MANIFEST_NAME}",
                    self.manifest_bytes,
                )
                self._add_file(
                    archive,
                    f"{_ARCHIVE_ROOT}/{_RUNNER_NAME}",
                    self.runner_bytes,
                    mode=0o755,
                )
                for relative, content in self.skill_files:
                    mode = 0o755 if "/scripts/" in f"/{relative}" else 0o644
                    self._add_file(
                        archive,
                        f"{_ARCHIVE_ROOT}/{_SKILLS_DIR}/{relative}",
                        content,
                        mode=mode,
                    )
        return target.getvalue()

    @staticmethod
    def _add_file(
        archive: tarfile.TarFile,
        path: str,
        content: bytes,
        *,
        mode: int = 0o644,
    ) -> None:
        info = tarfile.TarInfo(path)
        info.size = len(content)
        info.mode = mode
        info.mtime = 0
        info.uid = 0
        info.gid = 0
        info.uname = ""
        info.gname = ""
        archive.addfile(info, io.BytesIO(content))


__all__ = ["MigrationBundleError", "MigrationRunnerBundle"]
