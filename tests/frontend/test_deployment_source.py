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

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

import pytest

from frontend.server.deployment_source import (
    DeploymentSourceError,
    extract_migration_source,
    write_inline_source,
)


def _archive(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return output.getvalue()


def test_inline_source_uses_manifest_entry_and_keeps_app_py_fallback(
    tmp_path: Path,
) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    entry = write_inline_source(
        nested,
        [
            {
                "path": "agentkit.yaml",
                "content": (
                    "common:\n"
                    "  agent_name: support-agent\n"
                    "  entry_point: runtime/agent.py\n"
                ),
            },
            {"path": "runtime/agent.py", "content": "app = object()\n"},
        ],
    )
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    fallback = write_inline_source(
        legacy,
        [{"path": "app.py", "content": "app = object()\n"}],
    )

    assert entry == "runtime/agent.py"
    assert (nested / entry).read_text() == "app = object()\n"
    assert fallback == "app.py"


@pytest.mark.parametrize(
    ("files", "message"),
    [
        (
            [
                {
                    "path": "agentkit.yaml",
                    "content": "common:\n  entry_point: ../outside.py\n",
                },
                {"path": "app.py", "content": ""},
            ],
            "entry_point",
        ),
        (
            [
                {
                    "path": "agentkit.yaml",
                    "content": "common:\n  entry_point: missing.py\n",
                },
                {"path": "app.py", "content": ""},
            ],
            "missing.py",
        ),
        (
            [
                {"path": "bad\tname.py", "content": "app = object()\n"},
                {"path": "app.py", "content": ""},
            ],
            "安全的相对文件路径",
        ),
    ],
)
def test_inline_source_rejects_unsafe_or_missing_manifest_entry(
    tmp_path: Path,
    files: list[dict[str, str]],
    message: str,
) -> None:
    with pytest.raises(DeploymentSourceError, match=message):
        write_inline_source(tmp_path, files)


def test_inline_source_rejects_file_directory_path_collisions(
    tmp_path: Path,
) -> None:
    with pytest.raises(DeploymentSourceError, match="路径冲突"):
        write_inline_source(
            tmp_path,
            [
                {"path": "runtime", "content": "not a directory\n"},
                {"path": "runtime/app.py", "content": "app = object()\n"},
                {"path": "app.py", "content": "app = object()\n"},
            ],
        )


def test_migration_source_extracts_only_manifest_files(tmp_path: Path) -> None:
    content = b"app = object()\n"
    archive = _archive({"runtime/app.py": content})

    entry = extract_migration_source(
        tmp_path,
        archive,
        {
            "files": [
                {
                    "path": "runtime/app.py",
                    "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            ],
            "startup": {"module": "runtime/app.py"},
        },
    )

    assert entry == "runtime/app.py"
    assert (tmp_path / entry).read_bytes() == content


def test_migration_source_rejects_unlisted_archive_entry(tmp_path: Path) -> None:
    content = b"app = object()\n"
    archive = _archive({"app.py": content, "extra.py": b"secret\n"})

    with pytest.raises(DeploymentSourceError, match="文件清单"):
        extract_migration_source(
            tmp_path,
            archive,
            {
                "files": [
                    {
                        "path": "app.py",
                        "size": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                ],
                "startup": {"module": "app.py"},
            },
        )


def test_migration_source_rejects_file_directory_path_collisions(
    tmp_path: Path,
) -> None:
    files = {
        "runtime": b"not a directory\n",
        "runtime/app.py": b"app = object()\n",
    }
    manifest = {
        "files": [
            {
                "path": path,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
            for path, content in files.items()
        ],
        "startup": {"module": "runtime/app.py"},
    }

    with pytest.raises(DeploymentSourceError, match="路径冲突"):
        extract_migration_source(tmp_path, _archive(files), manifest)
