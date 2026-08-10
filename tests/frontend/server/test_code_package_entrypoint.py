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

"""Tests for Studio code-package entry-point resolution and bootstrapping."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from frontend.server.code_package_entrypoint import (
    prepare_code_package_launch_entry_point,
    resolve_code_package_entry_point,
)


def _write_files(base: Path, files: dict[str, str]) -> None:
    for relative_path, content in files.items():
        path = base / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


@pytest.mark.parametrize(
    ("files", "requested", "expected"),
    [
        ({"app.py": "", "agentkit_app.py": "", "main.py": ""}, None, "app.py"),
        ({"agentkit_app.py": ""}, None, "agentkit_app.py"),
        ({"main.py": ""}, None, "main.py"),
        ({"serve.py": ""}, None, "serve.py"),
        ({"nested folder/agent entry.py": ""}, None, "nested folder/agent entry.py"),
        (
            {
                "app.py": "",
                "agentkit_app.py": "",
                "migration-result.json": json.dumps({"entrypoint": "agentkit_app.py"}),
            },
            None,
            "agentkit_app.py",
        ),
        (
            {
                "app.py": "",
                "main.py": "",
                "migration-result.json": json.dumps({"entrypoint": "app.py"}),
            },
            "main.py",
            "main.py",
        ),
        (
            {
                "nested/serve.py": "",
                "migration-result.json": json.dumps(
                    {"entrypoint": "  nested/serve.py  "}
                ),
            },
            None,
            "nested/serve.py",
        ),
    ],
)
def test_resolve_code_package_entry_point(
    tmp_path: Path,
    files: dict[str, str],
    requested: str | None,
    expected: str,
) -> None:
    _write_files(tmp_path, files)

    assert resolve_code_package_entry_point(tmp_path, requested) == expected


@pytest.mark.parametrize(
    ("files", "requested", "message"),
    [
        ({"README.md": ""}, None, "No supported Python entry point found"),
        (
            {"first.py": "", "second.py": ""},
            None,
            "Multiple Python entry points found",
        ),
        ({"app.py": ""}, "../app.py", "safe relative Python file path"),
        ({"app.py": ""}, "app\n.py", "safe relative Python file path"),
        ({"app.py": ""}, "__init__.py", "safe relative Python file path"),
        ({"app.py": ""}, "missing.py", "does not exist in files"),
        (
            {"app.py": "", "migration-result.json": "{"},
            None,
            "must contain valid UTF-8 JSON",
        ),
        (
            {"app.py": "", "migration-result.json": "{}"},
            None,
            "must declare entrypoint",
        ),
        (
            {
                "app.py": "",
                "migration-result.json": json.dumps({"entrypoint": 1}),
            },
            None,
            "entrypoint must be a string",
        ),
        (
            {
                "app.py": "",
                "migration-result.json": json.dumps({"entrypoint": "../app.py"}),
            },
            "app.py",
            "safe relative Python file path",
        ),
    ],
)
def test_rejects_invalid_code_package_entry_point(
    tmp_path: Path,
    files: dict[str, str],
    requested: str | None,
    message: str,
) -> None:
    _write_files(tmp_path, files)

    with pytest.raises(ValueError, match=message):
        resolve_code_package_entry_point(tmp_path, requested)


@pytest.mark.parametrize(
    ("entry_point", "files"),
    [
        (
            "src/serve.py",
            {
                "src/__init__.py": "",
                "src/value.py": "VALUE = 'module-entry'\n",
                "src/serve.py": (
                    "from pathlib import Path\n"
                    "from .value import VALUE\n"
                    "Path('result.txt').write_text(VALUE, encoding='utf-8')\n"
                ),
            },
        ),
        (
            "nested folder/agent entry.py",
            {
                "nested folder/helper.py": "VALUE = 'path-entry'\n",
                "nested folder/agent entry.py": (
                    "from pathlib import Path\n"
                    "from helper import VALUE\n"
                    "Path('result.txt').write_text(VALUE, encoding='utf-8')\n"
                ),
            },
        ),
    ],
)
def test_prepared_entry_point_runs_with_agentkit_module_command(
    tmp_path: Path,
    entry_point: str,
    files: dict[str, str],
) -> None:
    _write_files(tmp_path, files)
    launch_entry_point = prepare_code_package_launch_entry_point(tmp_path, entry_point)

    result = subprocess.run(
        [sys.executable, "-m", Path(launch_entry_point).stem],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "result.txt").read_text(encoding="utf-8") in {
        "module-entry",
        "path-entry",
    }
