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

import asyncio
from types import SimpleNamespace

from google.adk.skills.models import Frontmatter, Resources, Script, Skill
from google.adk.tools import BaseTool
from google.adk.tools.skill_toolset import ListSkillsTool, SearchSkillsTool

from veadk.content_safety.adapters.skill import (
    AuditedSkillToolset,
    _result_audit_text,
    _skill_audit_text,
)


class FakeToolContext:
    def __init__(self):
        self.invocation_id = "inv"
        self.agent_name = "agent"
        self.state = {}


class RecordingAudit:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.calls = []

    async def __call__(self, invocation_id, text):
        self.calls.append((invocation_id, text))
        return self.allowed


class PlainTool(BaseTool):
    def __init__(self):
        super().__init__(name="plain", description="plain tool")

    async def run_async(self, *, args, tool_context):
        return {"ok": True}


def make_skill():
    return Skill(
        frontmatter=Frontmatter(name="demo", description="demo skill"),
        instructions="Do the thing.",
        resources=Resources(
            references={"ref.md": "reference body"},
            assets={"asset.bin": b"asset bytes"},
            scripts={"run.py": Script(src="print('hi')")},
        ),
    )


def make_toolset(audit, *, additional_tools=None):
    return AuditedSkillToolset(
        skills=[make_skill()],
        audit=audit,
        block_message="blocked by test",
        additional_tools=additional_tools or [],
    )


async def tools_by_name(toolset):
    return {tool.name: tool for tool in await toolset.get_tools(None)}


def test_get_tools_wraps_skill_tools_and_preserves_others():
    audit = RecordingAudit()
    plain = PlainTool()
    toolset = make_toolset(audit)
    tools = asyncio.run(tools_by_name(toolset))
    assert isinstance(tools["load_skill"], BaseTool)
    assert isinstance(tools["load_skill_resource"], BaseTool)
    assert isinstance(tools["run_skill_script"], BaseTool)
    assert tools["load_skill"]._get_declaration().name == "load_skill"
    assert toolset._wrap(plain) is plain


def test_load_skill_allow_audits_body_and_activates():
    audit = RecordingAudit(allowed=True)
    toolset = make_toolset(audit)
    load_skill = asyncio.run(tools_by_name(toolset))["load_skill"]
    context = FakeToolContext()

    result = asyncio.run(
        load_skill.run_async(args={"skill_name": "demo"}, tool_context=context)
    )

    assert result["instructions"] == "Do the thing."
    assert audit.calls[0][0] == "inv"
    assert "Do the thing." in audit.calls[0][1]
    assert "[skill_metadata]" in audit.calls[0][1]
    assert context.state["_adk_activated_skill_agent"] == ["demo"]


def test_load_skill_block_prevents_activation_and_returns_error():
    audit = RecordingAudit(allowed=False)
    toolset = make_toolset(audit)
    load_skill = asyncio.run(tools_by_name(toolset))["load_skill"]
    context = FakeToolContext()

    result = asyncio.run(
        load_skill.run_async(args={"skill_name": "demo"}, tool_context=context)
    )

    assert result == {"error": "blocked by test", "blocked": True}
    assert context.state == {}


def test_load_skill_missing_name_skips_audit():
    audit = RecordingAudit()
    toolset = make_toolset(audit)
    load_skill = asyncio.run(tools_by_name(toolset))["load_skill"]
    result = asyncio.run(load_skill.run_async(args={}, tool_context=FakeToolContext()))
    assert result["error_code"] == "INVALID_ARGUMENTS"
    assert audit.calls == []


def test_load_skill_unknown_skill_skips_audit():
    audit = RecordingAudit()
    toolset = make_toolset(audit)
    load_skill = asyncio.run(tools_by_name(toolset))["load_skill"]
    result = asyncio.run(
        load_skill.run_async(
            args={"skill_name": "missing"}, tool_context=FakeToolContext()
        )
    )
    assert result["error_code"] == "SKILL_NOT_FOUND"
    assert audit.calls == []


def test_skill_fetch_exception_fails_closed(monkeypatch):
    audit = RecordingAudit()
    toolset = make_toolset(audit)
    load_skill = asyncio.run(tools_by_name(toolset))["load_skill"]

    async def boom(*args, **kwargs):
        raise RuntimeError("registry down")

    monkeypatch.setattr(toolset, "_get_or_fetch_skill", boom)
    result = asyncio.run(
        load_skill.run_async(
            args={"skill_name": "demo"}, tool_context=FakeToolContext()
        )
    )
    assert result == {"error": "blocked by test", "blocked": True}
    assert audit.calls == []


def test_resource_reference_is_audited():
    audit = RecordingAudit()
    toolset = make_toolset(audit)
    tool = asyncio.run(tools_by_name(toolset))["load_skill_resource"]
    result = asyncio.run(
        tool.run_async(
            args={"skill_name": "demo", "file_path": "references/ref.md"},
            tool_context=FakeToolContext(),
        )
    )
    assert result["content"] == "reference body"
    assert "reference body" in audit.calls[0][1]
    assert "[skill_resource]" in audit.calls[0][1]


def test_resource_asset_bytes_are_decoded_for_audit():
    audit = RecordingAudit()
    toolset = make_toolset(audit)
    tool = asyncio.run(tools_by_name(toolset))["load_skill_resource"]
    result = asyncio.run(
        tool.run_async(
            args={"skill_name": "demo", "file_path": "assets/asset.bin"},
            tool_context=FakeToolContext(),
        )
    )
    assert result["status"]
    assert "asset bytes" in audit.calls[0][1]


def test_resource_script_source_is_audited():
    audit = RecordingAudit()
    toolset = make_toolset(audit)
    tool = asyncio.run(tools_by_name(toolset))["load_skill_resource"]
    result = asyncio.run(
        tool.run_async(
            args={"skill_name": "demo", "file_path": "scripts/run.py"},
            tool_context=FakeToolContext(),
        )
    )
    assert result["content"] == "print('hi')"
    assert "print('hi')" in audit.calls[0][1]


def test_resource_missing_path_skips_audit():
    audit = RecordingAudit()
    toolset = make_toolset(audit)
    tool = asyncio.run(tools_by_name(toolset))["load_skill_resource"]
    result = asyncio.run(
        tool.run_async(args={"skill_name": "demo"}, tool_context=FakeToolContext())
    )
    assert result["error_code"] == "INVALID_ARGUMENTS"
    assert audit.calls == []


def test_resource_unknown_path_skips_audit():
    audit = RecordingAudit()
    toolset = make_toolset(audit)
    tool = asyncio.run(tools_by_name(toolset))["load_skill_resource"]
    result = asyncio.run(
        tool.run_async(
            args={"skill_name": "demo", "file_path": "other/x"},
            tool_context=FakeToolContext(),
        )
    )
    assert result["error_code"] == "INVALID_RESOURCE_PATH"
    assert audit.calls == []


def test_resource_missing_content_skips_audit():
    audit = RecordingAudit()
    toolset = make_toolset(audit)
    tool = asyncio.run(tools_by_name(toolset))["load_skill_resource"]
    result = asyncio.run(
        tool.run_async(
            args={"skill_name": "demo", "file_path": "references/missing.md"},
            tool_context=FakeToolContext(),
        )
    )
    assert result["error_code"] == "RESOURCE_NOT_FOUND"
    assert audit.calls == []


def test_resource_block_prevents_returning_content():
    audit = RecordingAudit(allowed=False)
    toolset = make_toolset(audit)
    tool = asyncio.run(tools_by_name(toolset))["load_skill_resource"]
    result = asyncio.run(
        tool.run_async(
            args={"skill_name": "demo", "file_path": "references/ref.md"},
            tool_context=FakeToolContext(),
        )
    )
    assert result == {"error": "blocked by test", "blocked": True}


def test_script_block_prevents_execution():
    audit = RecordingAudit(allowed=False)
    toolset = make_toolset(audit)
    tool = asyncio.run(tools_by_name(toolset))["run_skill_script"]
    result = asyncio.run(
        tool.run_async(
            args={"skill_name": "demo", "file_path": "scripts/run.py"},
            tool_context=FakeToolContext(),
        )
    )
    assert result == {"error": "blocked by test", "blocked": True}
    assert "print('hi')" in audit.calls[0][1]


def test_script_audit_text_includes_arguments():
    toolset = make_toolset(RecordingAudit())
    script_tool = asyncio.run(tools_by_name(toolset))["run_skill_script"]
    text = asyncio.run(
        _skill_audit_text(
            script_tool._inner,
            {
                "skill_name": "demo",
                "file_path": "scripts/run.py",
                "args": {"x": 1},
            },
            FakeToolContext(),
        )
    )
    assert "[skill_script]" in text
    assert "print('hi')" in text
    assert '"x": 1' in text


def test_script_missing_script_skips_audit():
    audit = RecordingAudit()
    toolset = make_toolset(audit)
    tool = asyncio.run(tools_by_name(toolset))["run_skill_script"]
    result = asyncio.run(
        tool.run_async(
            args={"skill_name": "demo", "file_path": "scripts/missing.py"},
            tool_context=FakeToolContext(),
        )
    )
    assert result["error_code"] == "SCRIPT_NOT_FOUND"
    assert audit.calls == []


def test_unknown_skill_tool_type_returns_empty_text():
    class DummyTool(BaseTool):
        def __init__(self, toolset):
            super().__init__(name="dummy", description="dummy")
            self._toolset = toolset

        async def run_async(self, *, args, tool_context):
            return None

    toolset = make_toolset(RecordingAudit())
    text = asyncio.run(
        _skill_audit_text(
            DummyTool(toolset),
            {"skill_name": "demo", "file_path": "x"},
            FakeToolContext(),
        )
    )
    assert text == ""


class FakeRegistry:
    def search_tool_description(self):
        return "search"

    async def search_skills(self, *, query):
        assert query == "x"
        return [
            SimpleNamespace(
                name="remote",
                model_dump=lambda: {
                    "name": "remote",
                    "description": "remote skill",
                },
            )
        ]


def make_registry_toolset(audit):
    return AuditedSkillToolset(
        skills=[make_skill()],
        registry=FakeRegistry(),
        audit=audit,
        block_message="blocked by test",
    )


def test_list_skills_result_is_audited():
    audit = RecordingAudit()
    toolset = make_toolset(audit)
    tool = asyncio.run(tools_by_name(toolset))["list_skills"]
    assert tool._get_declaration().name == "list_skills"
    result = asyncio.run(tool.run_async(args={}, tool_context=FakeToolContext()))
    assert "demo skill" in result
    assert "[skill_list]" in audit.calls[0][1]
    assert "demo skill" in audit.calls[0][1]


def test_list_skills_block_prevents_returning_metadata():
    audit = RecordingAudit(allowed=False)
    toolset = make_toolset(audit)
    tool = asyncio.run(tools_by_name(toolset))["list_skills"]
    result = asyncio.run(tool.run_async(args={}, tool_context=FakeToolContext()))
    assert result == {"error": "blocked by test", "blocked": True}


def test_search_skills_result_is_audited():
    audit = RecordingAudit()
    toolset = make_registry_toolset(audit)
    tool = asyncio.run(tools_by_name(toolset))["search_skills"]
    result = asyncio.run(
        tool.run_async(args={"query": "x"}, tool_context=FakeToolContext())
    )
    assert result[0]["name"] == "remote"
    assert "[skill_search]" in audit.calls[0][1]
    assert "remote skill" in audit.calls[0][1]


def test_search_skills_block_prevents_returning_metadata():
    audit = RecordingAudit(allowed=False)
    toolset = make_registry_toolset(audit)
    tool = asyncio.run(tools_by_name(toolset))["search_skills"]
    result = asyncio.run(
        tool.run_async(args={"query": "x"}, tool_context=FakeToolContext())
    )
    assert result == {"error": "blocked by test", "blocked": True}


def test_result_audit_text_ignores_empty_or_unrelated_results():
    list_tool = object.__new__(ListSkillsTool)
    search_tool = object.__new__(SearchSkillsTool)
    assert _result_audit_text(list_tool, "") == ""
    assert _result_audit_text(list_tool, ["not", "a", "string"]) == ""
    assert _result_audit_text(search_tool, []) == ""
    assert _result_audit_text(search_tool, {"not": "a list"}) == ""
    assert _result_audit_text(PlainTool(), "anything") == ""
