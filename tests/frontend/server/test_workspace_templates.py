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

from pathlib import Path
import runpy
from unittest.mock import patch

import pytest

from frontend.server.workspace_templates import default_project_template

runtime = runpy.run_path(
    str(
        Path(__file__).parents[3]
        / "frontend/sandbox-image/runtime/studio-project-create"
    )
)


def test_studio_template_has_clean_imports_and_named_agent():
    files = default_project_template("test-agent")["files"]
    assert files["main.py"].startswith("from veadk import Agent\n\nagent = ")
    assert 'name="test_agent"' in files["main.py"]
    assert "# test-agent" in files["README.md"]
    assert {".gitignore", "AGENTS.md", "README.md", "main.py"} <= files.keys()


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "/absolute",
        "nested/../../escape",
        ".git/config",
        ".venv/bin/python",
        "a\\b",
        "a//b",
    ],
)
def test_invalid_template_fails_before_project_creation(tmp_path, name):
    with patch("subprocess.run") as run:
        with pytest.raises(ValueError):
            runtime["create_project"](
                "demo",
                tmp_path,
                tmp_path,
                template={"version": 1, "files": {name: "bad"}},
            )
        run.assert_not_called()
    assert not (tmp_path / "demo").exists()


def test_custom_template_is_written_without_fallback_main(tmp_path):
    template = {
        "version": 1,
        "files": {"app/main.py": 'print("custom")\n', "README.md": "# My template\n"},
    }
    with patch("subprocess.run"):
        project = runtime["create_project"](
            "demo", tmp_path, tmp_path, template=template
        )
    assert (project / "app/main.py").read_text() == 'print("custom")\n'
    assert (project / "README.md").read_text() == "# My template\n"
    assert not (project / "main.py").exists()
    assert (project / "AGENTS.md").exists()
    with pytest.raises(FileExistsError):
        runtime["create_project"]("demo", tmp_path, tmp_path, template=template)


@pytest.mark.parametrize(
    "files", [{"a": "file", "a/b": "child"}, {"main.py": "x" * 1_048_577}]
)
def test_template_rejects_conflicts_and_oversize(files):
    with pytest.raises(ValueError):
        runtime["validate_template"]({"version": 1, "files": files})


def test_unsupported_byteplus_region_requires_explicit_image(monkeypatch):
    from frontend.server.workspace_tool import provision_workspace_tool

    monkeypatch.delenv("STUDIO_WORKSPACE_IMAGE", raising=False)
    with pytest.raises(ValueError, match="STUDIO_WORKSPACE_IMAGE"):
        provision_workspace_tool(
            provider="byteplus",
            region="unsupported-region",
            access_key="test",
            secret_key="test",
        )
