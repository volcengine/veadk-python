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

"""CUA dependency gating must not skip unrelated repository tests."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("installed", [False, True])
@pytest.mark.parametrize("workers", [0, 2])
def test_cua_collection_scope(tmp_path, installed, workers):
    cua = tmp_path / "tests" / "tools" / "cua_mcp"
    cua.mkdir(parents=True)
    sibling = tmp_path / "tests" / "tools" / "cua_mcp_extra"
    sibling.mkdir()
    shutil.copy2(ROOT / "tests/tools/cua_mcp/conftest.py", cua / "conftest.py")
    (tmp_path / "conftest.py").write_text(
        "import importlib.util\n"
        "original = importlib.util.find_spec\n"
        "def find_spec(name, *args, **kwargs):\n"
        f"    if name == 'agentkit_cua_mcp': return {'object()' if installed else 'None'}\n"
        "    return original(name, *args, **kwargs)\n"
        "importlib.util.find_spec = find_spec\n"
    )
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (cua / "test_cua.py").write_text("def test_cua(): pass\n")
    (sibling / "test_sibling.py").write_text("def test_sibling(): pass\n")
    (tmp_path / "tests/test_unrelated.py").write_text("def test_unrelated(): pass\n")
    report = tmp_path / "result.xml"
    command = [sys.executable, "-m", "pytest", "-q", f"--junitxml={report}"]
    if workers:
        command += ["-p", "xdist.plugin", "-n", str(workers)]
    environment = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    environment.pop("PYTEST_ADDOPTS", None)
    run = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    cases = ET.parse(report).findall(".//testcase")
    assert len(cases) == 3
    skipped = [
        case.attrib["name"] for case in cases if case.find("skipped") is not None
    ]
    assert skipped == ([] if installed else ["test_cua"])
