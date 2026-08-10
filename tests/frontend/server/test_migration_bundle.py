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

from __future__ import annotations

import io
import json
import shutil
import tarfile
from pathlib import Path

import pytest
import veadk

from frontend.server.migration.bundle import (
    MigrationBundleError,
    MigrationRunnerBundle,
)


def _asset_root() -> Path:
    return Path(veadk.__file__).parent / "assets" / "migration"


def test_loads_verified_self_contained_runner_bundle() -> None:
    bundle = MigrationRunnerBundle.load()

    assert bundle.agentkit_cli_version == "0.51.1"
    assert bundle.source_commit == "a1fc1a61b204c2c98b779e4f81fcfd63fe103609"
    assert bundle.capabilities["frameworks"] == [
        "langchain",
        "langgraph",
        "adk",
        "strands",
        "agentcore",
        "dify",
        "any",
    ]
    assert {
        "source-to-veadk/SKILL.md",
        "agentkit-cli/SKILL.md",
        "veadk-agent-development/SKILL.md",
    } <= {path for path, _ in bundle.skill_files}


def test_builds_deterministic_safe_runtime_archive() -> None:
    bundle = MigrationRunnerBundle.load()

    first = bundle.archive()
    assert first == bundle.archive()
    with tarfile.open(fileobj=io.BytesIO(first), mode="r:gz") as archive:
        members = archive.getmembers()
        names = {member.name for member in members}
        runner = archive.getmember("agentkit-migration-runtime/runner.mjs")
        script = archive.getmember(
            "agentkit-migration-runtime/skills/"
            "source-to-veadk/scripts/validate_runtime.sh"
        )

    assert "agentkit-migration-runtime/bundle-manifest.json" in names
    assert all(member.isfile() for member in members)
    assert all(
        not member.name.startswith("/") and ".." not in member.name
        for member in members
    )
    assert runner.mode == 0o755
    assert script.mode == 0o755


@pytest.mark.parametrize("target", ["runner", "skills", "capabilities"])
def test_rejects_tampered_or_incompatible_bundle(
    tmp_path: Path,
    target: str,
) -> None:
    root = tmp_path / "migration"
    shutil.copytree(_asset_root(), root)
    if target == "runner":
        (root / "runner.mjs").write_text("tampered\n", encoding="utf-8")
    elif target == "skills":
        (root / "skills/source-to-veadk/SKILL.md").write_text(
            "tampered\n",
            encoding="utf-8",
        )
    else:
        manifest_path = root / "bundle-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["capabilities"]["frameworks"] = ["any"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(MigrationBundleError):
        MigrationRunnerBundle.load(root)
