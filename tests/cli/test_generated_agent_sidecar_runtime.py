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

from importlib import metadata
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from veadk.cli.generated_agent_sidecar_runtime import (
    GeneratedAgentSidecarRuntimeUnavailable,
    installed_harness_sidecar_runtime_command,
)


def test_installed_runtime_command_executes_distribution_entry_point(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    site_packages = tmp_path / "site-packages"
    site_packages.mkdir()
    (site_packages / "sidecar_runtime_fixture.py").write_text(
        """import json
import sys


def main():
    print(json.dumps({"argv": sys.argv[1:]}))
    return 0
""",
        encoding="utf-8",
    )
    dist_info = site_packages / "bytedance_agentkit_harness_sidecar-0.0.test.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        """Metadata-Version: 2.1
Name: bytedance-agentkit-harness-sidecar
Version: 0.0.test
""",
        encoding="utf-8",
    )
    (dist_info / "entry_points.txt").write_text(
        """[console_scripts]
agentkit-harness-sidecar-runtime = sidecar_runtime_fixture:main
""",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(site_packages))

    command = installed_harness_sidecar_runtime_command()
    environment = os.environ.copy()
    source_root = str(Path(__file__).resolve().parents[2])
    environment["PYTHONPATH"] = os.pathsep.join(
        value
        for value in (
            str(site_packages),
            source_root,
            environment.get("PYTHONPATH", ""),
        )
        if value
    )
    completed = subprocess.run(
        [*command, "doctor", "--json"],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert command == (
        sys.executable,
        "-m",
        "veadk.cli.generated_agent_sidecar_runtime",
    )
    assert completed.returncode == 0
    assert json.loads(completed.stdout) == {"argv": ["doctor", "--json"]}
    assert completed.stderr == ""


def test_installed_runtime_command_fails_closed_without_distribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_distribution(_name: str) -> metadata.Distribution:
        raise metadata.PackageNotFoundError

    monkeypatch.setattr(metadata, "distribution", missing_distribution)

    with pytest.raises(
        GeneratedAgentSidecarRuntimeUnavailable,
        match="debug runtime is not installed",
    ):
        installed_harness_sidecar_runtime_command()
