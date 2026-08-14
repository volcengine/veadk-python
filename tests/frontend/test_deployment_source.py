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
import stat
import zipfile
from pathlib import Path

import pytest

from frontend.server import deployment_source
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


@pytest.mark.parametrize(
    "content",
    [
        b"root_agent.run = custom_run\n",
        b"setattr(agent, 'run_async', custom_run)\n",
    ],
)
def test_migration_source_rejects_agent_runtime_method_replacement(
    tmp_path: Path,
    content: bytes,
) -> None:
    manifest = {
        "files": [
            {
                "path": "agent.py",
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        ],
        "startup": {"module": "agent.py"},
    }

    with pytest.raises(DeploymentSourceError, match="Runtime 调用兼容性"):
        extract_migration_source(tmp_path, _archive({"agent.py": content}), manifest)


def test_migration_source_allows_agent_method_definitions(tmp_path: Path) -> None:
    content = b"class Agent:\n    async def run_async(self):\n        return None\n"
    manifest = {
        "files": [
            {
                "path": "agent.py",
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        ],
        "startup": {"module": "agent.py"},
    }

    assert (
        extract_migration_source(
            tmp_path,
            _archive({"agent.py": content}),
            manifest,
        )
        == "agent.py"
    )


def test_migration_source_rejects_invalid_python(tmp_path: Path) -> None:
    content = b"def broken(:\n"
    manifest = {
        "files": [
            {
                "path": "agent.py",
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        ],
        "startup": {"module": "agent.py"},
    }

    with pytest.raises(DeploymentSourceError, match="无法解析"):
        extract_migration_source(tmp_path, _archive({"agent.py": content}), manifest)


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


@pytest.mark.parametrize(
    ("files", "message"),
    [
        (None, "No files provided"),
        (["app.py"], "格式无效"),
        ([{"path": 1, "content": ""}], "必须是相对文件路径"),
        (
            [
                {"path": "app.py", "content": ""},
                {"path": "app.py", "content": ""},
            ],
            "重复",
        ),
        ([{"path": "app.py", "content": b"binary"}], "必须是文本"),
    ],
)
def test_inline_source_rejects_invalid_file_descriptors(
    tmp_path: Path,
    files: object,
    message: str,
) -> None:
    with pytest.raises(DeploymentSourceError, match=message):
        write_inline_source(tmp_path, files)


@pytest.mark.parametrize(
    ("manifest", "message"),
    [
        ("- item\n", "根节点必须是对象"),
        ("common: value\n", "common 必须是对象"),
        ("common:\n  entry_point: [app.py]\n", "必须是相对文件路径"),
        ("common: [\n", "无法解析"),
    ],
)
def test_inline_source_rejects_invalid_agentkit_manifest(
    tmp_path: Path,
    manifest: str,
    message: str,
) -> None:
    with pytest.raises(DeploymentSourceError, match=message):
        write_inline_source(
            tmp_path,
            [
                {"path": "agentkit.yaml", "content": manifest},
                {"path": "app.py", "content": "app = object()\n"},
            ],
        )


@pytest.mark.parametrize("manifest", ["", "{}\n", "common: {}\n"])
def test_inline_source_manifest_defaults_to_app_py(
    tmp_path: Path,
    manifest: str,
) -> None:
    assert (
        write_inline_source(
            tmp_path,
            [
                {"path": "agentkit.yaml", "content": manifest},
                {"path": "app.py", "content": "app = object()\n"},
            ],
        )
        == "app.py"
    )


def test_deployment_target_guard_rejects_path_escape(tmp_path: Path) -> None:
    with pytest.raises(DeploymentSourceError, match="路径越界"):
        deployment_source._target(tmp_path, "../outside.py")


@pytest.mark.parametrize(
    ("manifest", "message"),
    [
        (None, "清单格式无效"),
        ({"files": [], "startup": {}}, "文件清单格式无效"),
        ({"files": ["app.py"], "startup": {}}, "文件清单格式无效"),
        (
            {
                "files": [{"path": "app.py", "size": True, "sha256": "0" * 64}],
                "startup": {"module": "app.py"},
            },
            "文件清单格式无效",
        ),
        (
            {
                "files": [{"path": "app.py", "size": 1, "sha256": "0" * 64}],
                "startup": {"module": "missing.py"},
            },
            "启动文件不在文件清单",
        ),
    ],
)
def test_migration_source_rejects_invalid_manifests(
    tmp_path: Path,
    manifest: object,
    message: str,
) -> None:
    with pytest.raises(DeploymentSourceError, match=message):
        extract_migration_source(tmp_path, _archive({"app.py": b"x"}), manifest)


def test_migration_source_enforces_archive_and_expansion_limits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    with pytest.raises(DeploymentSourceError, match="ZIP 大小无效"):
        extract_migration_source(tmp_path, b"", {})

    monkeypatch.setattr(deployment_source, "_MAX_EXPANDED_BYTES", 0)
    with pytest.raises(DeploymentSourceError, match="解压后超过"):
        extract_migration_source(
            tmp_path,
            _archive({"app.py": b"x"}),
            {
                "files": [
                    {
                        "path": "app.py",
                        "size": 1,
                        "sha256": hashlib.sha256(b"x").hexdigest(),
                    }
                ],
                "startup": {"module": "app.py"},
            },
        )


def test_migration_source_rejects_unsafe_and_corrupt_entries(tmp_path: Path) -> None:
    content = b"app = object()\n"
    digest = hashlib.sha256(content).hexdigest()
    manifest = {
        "files": [{"path": "app.py", "size": len(content), "sha256": digest}],
        "startup": {"module": "app.py"},
    }

    unsafe = io.BytesIO()
    link = zipfile.ZipInfo("app.py")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr(link, content)
    with pytest.raises(DeploymentSourceError, match="不安全文件"):
        extract_migration_source(tmp_path, unsafe.getvalue(), manifest)

    with pytest.raises(DeploymentSourceError, match="完整性校验失败"):
        extract_migration_source(
            tmp_path,
            _archive({"app.py": content}),
            {
                "files": [{"path": "app.py", "size": len(content), "sha256": "0" * 64}],
                "startup": {"module": "app.py"},
            },
        )
