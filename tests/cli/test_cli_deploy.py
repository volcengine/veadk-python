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

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from click.testing import CliRunner

from veadk.cli.cli_deploy import deploy
from veadk.config import veadk_environments


def _write_agent_project(path: Path) -> None:
    path.mkdir()
    (path / "__init__.py").write_text("from . import agent\n", encoding="utf-8")
    (path / "agent.py").write_text("root_agent = object()\n", encoding="utf-8")


def test_deploy_reads_byteplus_provider_environment(
    monkeypatch,
    tmp_path: Path,
) -> None:
    project = tmp_path / "agent-proj"
    _write_agent_project(project)
    captured: dict[str, Any] = {}

    def fake_cookiecutter(
        template: str,
        output_dir: str,
        no_input: bool,
        extra_context: dict[str, Any],
    ) -> None:
        captured["template"] = template
        captured["no_input"] = no_input
        captured["extra_context"] = extra_context
        generated_agent_dir = (
            Path(output_dir) / extra_context["local_dir_name"] / "src" / "agent_proj"
        )
        generated_agent_dir.mkdir(parents=True)

    async def fake_main() -> None:
        captured["main_env"] = {
            "CLOUD_PROVIDER": os.environ.get("CLOUD_PROVIDER"),
            "AGENTKIT_CLOUD_PROVIDER": os.environ.get("AGENTKIT_CLOUD_PROVIDER"),
            "BYTEPLUS_REGION": os.environ.get("BYTEPLUS_REGION"),
            "REGION": os.environ.get("REGION"),
            "VOLCENGINE_ACCESS_KEY": os.environ.get("VOLCENGINE_ACCESS_KEY"),
            "VOLCENGINE_SECRET_KEY": os.environ.get("VOLCENGINE_SECRET_KEY"),
            "VOLCENGINE_SESSION_TOKEN": os.environ.get("VOLCENGINE_SESSION_TOKEN"),
        }

    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.delenv("AGENTKIT_CLOUD_PROVIDER", raising=False)
    monkeypatch.delenv("REGION", raising=False)
    monkeypatch.delenv("VOLCENGINE_ACCESS_KEY", raising=False)
    monkeypatch.delenv("VOLCENGINE_SECRET_KEY", raising=False)
    monkeypatch.delenv("VOLCENGINE_SESSION_TOKEN", raising=False)
    monkeypatch.setenv("BYTEPLUS_REGION", "ap-southeast-1")
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "byteplus-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "byteplus-sk")
    monkeypatch.setenv("BYTEPLUS_SESSION_TOKEN", "byteplus-token")
    for key in (
        "CLOUD_PROVIDER",
        "AGENTKIT_CLOUD_PROVIDER",
        "BYTEPLUS_REGION",
    ):
        monkeypatch.delitem(veadk_environments, key, raising=False)
    monkeypatch.setattr("veadk.utils.misc.formatted_timestamp", lambda: "20260824")
    monkeypatch.setattr("cookiecutter.main.cookiecutter", fake_cookiecutter)
    monkeypatch.setattr(
        "veadk.utils.misc.load_module_from_file",
        lambda **_kwargs: SimpleNamespace(main=fake_main),
    )

    result = CliRunner().invoke(
        deploy,
        [
            "--vefaas-app-name",
            "studio-app",
            "--path",
            str(project),
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["extra_context"]["provider"] == "byteplus"
    assert captured["extra_context"]["region"] == "ap-southeast-1"
    assert captured["main_env"] == {
        "CLOUD_PROVIDER": "byteplus",
        "AGENTKIT_CLOUD_PROVIDER": "byteplus",
        "BYTEPLUS_REGION": "ap-southeast-1",
        "REGION": "ap-southeast-1",
        "VOLCENGINE_ACCESS_KEY": "byteplus-ak",
        "VOLCENGINE_SECRET_KEY": "byteplus-sk",
        "VOLCENGINE_SESSION_TOKEN": "byteplus-token",
    }
