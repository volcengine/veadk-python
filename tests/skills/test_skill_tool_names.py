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

"""Execution guidance must use names that the toolset actually declares."""

from google.adk.tools import FunctionTool

from veadk.tools.skills_tools.bash_tool import bash_tool
from veadk.tools.skills_tools.skills_tool import SkillsTool
from veadk.tools.skills_tools.skills_toolset import SkillsToolset


def test_skill_description_uses_registered_shell_tool_name():
    toolset = SkillsToolset({}, "local")
    shell_name = toolset._tools["bash"]._get_declaration().name
    assert shell_name == FunctionTool(bash_tool)._get_declaration().name
    assert f"use the `{shell_name}` tool" in toolset._tools["skills"].description
    assert "use the bash tool" not in toolset._tools["skills"].description


def test_loaded_skill_footer_uses_registered_name_and_preserves_body():
    body = "# Demo\nAuthor's instructions: use bash syntax; do not rewrite this.\n"
    rendered = SkillsTool({})._format_skill_content("demo", body, "/workspace/skills")
    assert body in rendered
    footer = rendered.split("\n\n---\n")[-1]
    shell_name = FunctionTool(bash_tool)._get_declaration().name
    assert f"use the `{shell_name}` tool" in footer
    assert "use the bash tool" not in footer
