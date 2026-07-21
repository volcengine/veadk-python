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

import py_compile
import socket

import pytest
from pydantic import ValidationError

from veadk.cli.generated_agent_codegen import (
    AgentDraft,
    GeneratedAgentProjectRequest,
    GeneratedAgentTestRunRequest,
    GeneratedFile,
    GeneratedProject,
    SelectedSkill,
    generate_project_from_draft,
)
from veadk.cli.generated_agent_security import (
    DebugPolicyError,
    validate_debug_policy,
    validate_project_policy,
    validate_url_not_private,
)
from veadk.cli.generated_agent_skills import materialize_selected_skills


def test_old_files_request_shape_is_rejected() -> None:
    payload = {
        "name": "demo",
        "files": [{"path": "agents/demo/agent.py", "content": "root_agent = None"}],
    }
    with pytest.raises(ValidationError):
        GeneratedAgentProjectRequest.model_validate(payload)
    with pytest.raises(ValidationError):
        GeneratedAgentTestRunRequest.model_validate(payload)


def test_minimal_codegen_agent_py_compiles(tmp_path) -> None:
    draft = AgentDraft(
        name="demo-agent",
        description="Demo agent",
        instruction='Say "hello" and handle """triple""" quotes \\ safely.',
    )
    project = generate_project_from_draft(draft)

    assert project.name == "demo_agent"
    paths = {file.path for file in project.files}
    assert "app.py" in paths
    assert "agents/demo_agent/agent.py" in paths
    assert "agents/demo_agent/__init__.py" in paths
    assert ".env.example" in paths
    assert "requirements.txt" in paths

    for file in project.files:
        if file.path.endswith(".py"):
            target = tmp_path / file.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(file.content, encoding="utf-8")
            py_compile.compile(str(target), doraise=True)


def test_security_rejects_unsupported_builtin_tool() -> None:
    draft = AgentDraft(
        name="demo",
        instruction="You are helpful.",
        builtinTools=["not_a_tool"],
    )
    with pytest.raises(DebugPolicyError):
        validate_debug_policy(draft)


def test_security_rejects_mcp_stdio() -> None:
    draft = AgentDraft(
        name="demo",
        instruction="You are helpful.",
        mcpTools=[{"transport": "stdio", "command": "npx"}],
    )
    with pytest.raises(DebugPolicyError):
        validate_debug_policy(draft)


def test_project_policy_allows_mcp_stdio_but_debug_rejects_it() -> None:
    draft = AgentDraft(
        name="demo",
        instruction="You are helpful.",
        mcpTools=[{"transport": "stdio", "command": "npx", "args": ["-y", "mcp"]}],
    )

    validate_project_policy(draft)
    with pytest.raises(DebugPolicyError):
        validate_debug_policy(draft, allow_local_runtime_resources=True)


def test_security_rejects_enabled_a2a_registry_without_space_id() -> None:
    draft = AgentDraft(
        name="demo",
        instruction="You are helpful.",
        a2aRegistry={"enabled": True},
    )
    with pytest.raises(DebugPolicyError, match="A2A registry space id is required"):
        validate_project_policy(draft)


def test_url_policy_rejects_private_literal_ip() -> None:
    with pytest.raises(DebugPolicyError):
        validate_url_not_private("http://127.0.0.1:8000", field_name="url")
    with pytest.raises(DebugPolicyError):
        validate_url_not_private("http://169.254.169.254/latest", field_name="url")


def test_url_policy_rejects_dns_to_private_ip(monkeypatch) -> None:
    def fake_getaddrinfo(*args, **kwargs):
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("10.0.0.8", 443),
            )
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(DebugPolicyError):
        validate_url_not_private("https://example.com", field_name="url")


@pytest.mark.asyncio
async def test_local_skill_materialization_accepts_safe_skill() -> None:
    skill_md = "---\nname: local-skill\ndescription: Local skill.\n---\n\n# Local\n"
    draft = AgentDraft(
        name="demo",
        instruction="You are helpful.",
        selectedSkills=[
            SelectedSkill(
                source="local",
                folder="local-skill",
                name="local-skill",
                localFiles=[
                    GeneratedFile(
                        path="skills/local-skill/SKILL.md",
                        content=skill_md,
                    )
                ],
            )
        ],
    )
    project = GeneratedProject(name="demo", files=[])

    await materialize_selected_skills(draft, project)

    assert project.files == [
        GeneratedFile(path="skills/local-skill/SKILL.md", content=skill_md)
    ]


@pytest.mark.asyncio
async def test_local_skill_materialization_rejects_path_escape() -> None:
    skill_md = "---\nname: local-skill\ndescription: Local skill.\n---\n"
    draft = AgentDraft(
        name="demo",
        instruction="You are helpful.",
        selectedSkills=[
            SelectedSkill(
                source="local",
                folder="local-skill",
                name="local-skill",
                localFiles=[
                    GeneratedFile(
                        path="skills/local-skill/SKILL.md",
                        content=skill_md,
                    ),
                    GeneratedFile(path="../evil.py", content="print('bad')"),
                ],
            )
        ],
    )
    project = GeneratedProject(name="demo", files=[])

    with pytest.raises(DebugPolicyError):
        await materialize_selected_skills(draft, project)
