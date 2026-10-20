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

"""Studio-owned project templates sent to the Sandbox initialization tool."""

from pathlib import Path
from string import Template

from frontend.server.workspace_preview import ProjectInput


def default_project_template(name: str) -> dict[str, object]:
    ProjectInput(name=name)
    root = Path(__file__).parent / "templates" / "python-agent"
    files = {
        path.name.removesuffix(".tmpl"): Template(
            path.read_text(encoding="utf-8")
        ).substitute(project_name=name, agent_name=name.replace("-", "_"))
        for path in sorted(root.glob("*.tmpl"))
    }
    if "main.py" not in files:
        raise ValueError("Studio default project template is missing")
    return {"version": 1, "files": files}
