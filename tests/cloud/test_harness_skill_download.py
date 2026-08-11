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

"""Offline tests for HarnessApp skill download resolution."""

from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace

import httpx
import pytest
from google.adk.agents import LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.code_executors import UnsafeLocalCodeExecutor
from google.adk.sessions import InMemorySessionService, Session
from google.adk.skills import load_skill_from_dir
from google.adk.tools import ToolContext
from google.adk.tools.skill_toolset import SkillToolset

from veadk.cloud.harness_app import utils
from veadk.skills.skill import Skill as VeADKSkill


def _skill_zip_bytes(name: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "SKILL.md",
            f"---\nname: {name}\ndescription: Test skill.\n---\n\n# {name}\n",
        )
    return buffer.getvalue()


def _write_adk_skill(path, *, name: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Test skill.\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def test_download_skill_resolves_short_name_to_exact_slug(monkeypatch, tmp_path):
    calls: list[str] = []

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        calls.append(url)
        request = httpx.Request("GET", url)
        if url.endswith("/download/web-scraper"):
            return httpx.Response(
                200,
                request=request,
                json={
                    "ResponseMetadata": {
                        "Action": "DownloadSkill",
                        "Error": {"Code": "NotFound"},
                    }
                },
            )
        if "/v1/skills?" in url:
            return httpx.Response(
                200,
                request=request,
                json={
                    "Skills": [
                        {
                            "Name": "web-scraper",
                            "Slug": "clawhub/example/web-scraper",
                            "SourceRepo": "clawhub/example",
                        }
                    ]
                },
            )
        if url.endswith("/download/clawhub/example/web-scraper"):
            return httpx.Response(
                200,
                request=request,
                content=_skill_zip_bytes("web-scraper"),
            )
        return httpx.Response(404, request=request)

    monkeypatch.setattr(utils.httpx, "get", fake_get)

    extracted = utils._download_and_extract_skill("web-scraper", tmp_path)

    assert extracted == tmp_path / "web-scraper"
    assert (extracted / "SKILL.md").is_file()
    assert calls == [
        "https://skills.volces.com/v1/skills/download/web-scraper",
        "https://skills.volces.com/v1/skills?query=web-scraper&pageNumber=1&pageSize=10",
        "https://skills.volces.com/v1/skills/download/clawhub/example/web-scraper",
    ]


def test_build_skill_toolset_loads_skills_center_space(monkeypatch, tmp_path):
    calls: list[str] = []
    remote_skill = VeADKSkill(
        name="center-skill",
        description="Center skill.",
        path="skills/s-123/v1/center-skill.zip",
        skill_space_id="ss-test",
        bucket_name="bucket",
        id="s-123",
    )

    def fake_load_skills_from_space_id(skill_space_id: str) -> list[VeADKSkill]:
        calls.append(skill_space_id)
        return [remote_skill]

    def fake_materialize_remote_skill(
        skill: VeADKSkill,
        *,
        cache_dir=None,
    ):
        assert skill == remote_skill
        assert cache_dir == tmp_path
        skill_dir = tmp_path / skill.name
        _write_adk_skill(skill_dir, name=skill.name)
        return skill_dir

    def fail_skillhub_download(*args, **kwargs):
        raise AssertionError("skills-center refs must not use SkillHub download")

    monkeypatch.setattr(
        utils,
        "_load_skills_from_space_id",
        fake_load_skills_from_space_id,
    )
    monkeypatch.setattr(
        utils,
        "materialize_remote_skill",
        fake_materialize_remote_skill,
    )
    monkeypatch.setattr(utils, "_download_and_extract_skill", fail_skillhub_download)

    toolset = utils.build_skill_toolset(["space:ss-test"], download_dir=tmp_path)

    assert calls == ["ss-test"]
    assert [skill.name for skill in toolset._list_skills()] == ["center-skill"]
    assert isinstance(toolset._code_executor, UnsafeLocalCodeExecutor)


def test_incremental_skills_preserve_existing_code_executor(monkeypatch, tmp_path):
    existing_dir = tmp_path / "existing"
    incoming_dir = tmp_path / "incoming"
    _write_adk_skill(existing_dir, name="existing")
    _write_adk_skill(incoming_dir, name="incoming")

    executor = UnsafeLocalCodeExecutor()
    existing_toolset = SkillToolset(
        skills=[load_skill_from_dir(existing_dir)],
        code_executor=executor,
    )
    incoming_toolset = SkillToolset(
        skills=[load_skill_from_dir(incoming_dir)],
        code_executor=UnsafeLocalCodeExecutor(),
    )
    agent = SimpleNamespace(tools=[existing_toolset])
    monkeypatch.setattr(
        utils,
        "build_skill_toolset",
        lambda skill_ids, download_dir=None: incoming_toolset,
    )

    utils._add_incremental_skills(agent, ["incoming"])

    merged_toolset = agent.tools[0]
    assert [skill.name for skill in merged_toolset._list_skills()] == [
        "existing",
        "incoming",
    ]
    assert merged_toolset._code_executor is executor


@pytest.mark.asyncio
async def test_build_skill_toolset_runs_python_script(monkeypatch, tmp_path):
    skill_dir = tmp_path / "python-sum"
    _write_adk_skill(skill_dir, name="python-sum")
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "add.py").write_text(
        "import sys\nprint(int(sys.argv[1]) + int(sys.argv[2]))\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        utils,
        "_download_and_extract_skill",
        lambda skill, download_dir: skill_dir,
    )

    toolset = utils.build_skill_toolset(["python-sum"], download_dir=tmp_path)
    run_script = next(
        tool for tool in await toolset.get_tools() if tool.name == "run_skill_script"
    )
    agent = LlmAgent(name="test_agent", model="gemini-2.0-flash")
    invocation_context = InvocationContext(
        session_service=InMemorySessionService(),
        invocation_id="test-invocation",
        agent=agent,
        session=Session(
            id="test-session",
            appName=agent.name,
            userId="test-user",
        ),
    )

    result = await run_script.run_async(
        args={
            "skill_name": "python-sum",
            "file_path": "scripts/add.py",
            "args": ["17", "25"],
        },
        tool_context=ToolContext(invocation_context),
    )

    assert result == {
        "skill_name": "python-sum",
        "file_path": "scripts/add.py",
        "stdout": "42\n",
        "stderr": "",
        "status": "success",
    }
