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

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from veadk.cli import frontend_coding_agents as coding_agents

SKILLS = {
    "agentkit-cli": "AgentKit 平台操作技能",
}


def _write_bundled_skills(root: Path) -> Path:
    for skill_id, label in SKILLS.items():
        skill = root / skill_id
        (skill / "references").mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            f"---\nname: {skill_id}\ndescription: {label}\n---\nUse it.\n",
            encoding="utf-8",
        )
        (skill / "references" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    return root


def _app(home: Path, bundled_skills: Path) -> FastAPI:
    app = FastAPI()
    coding_agents.mount_coding_agent_routes(
        app,
        authorize=lambda request: None,
        home_dir=home,
        bundled_skills_dir=bundled_skills,
    )
    return app


@pytest.fixture
def bundled_skills(tmp_path: Path) -> Path:
    return _write_bundled_skills(tmp_path / "bundled-skills")


@pytest.mark.parametrize(
    ("system", "platform_id", "expected_prefix"),
    [
        ("Darwin", "macos", "~/"),
        ("Linux", "linux", "~/"),
        ("Windows", "windows", "%USERPROFILE%\\"),
    ],
)
def test_capabilities_are_cross_platform_and_report_global_directories(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    bundled_skills: Path,
    system: str,
    platform_id: str,
    expected_prefix: str,
) -> None:
    executables = {
        "trae": "/tools/trae",
        "claude": "/tools/claude",
        "codex": "/tools/codex",
    }
    monkeypatch.setattr(coding_agents.platform, "system", lambda: system)
    monkeypatch.setattr(coding_agents.shutil, "which", executables.get)
    monkeypatch.setattr(
        coding_agents.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="1.2.3\n", stderr=""),
    )

    response = TestClient(_app(tmp_path / "home", bundled_skills)).get(
        "/web/coding-agents/capabilities"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["platform"] == platform_id
    assert [item["id"] for item in body["agents"]] == [
        "trae",
        "claude-code",
        "codex",
    ]
    assert all(item["available"] for item in body["agents"])
    assert all(item["version"] == "1.2.3" for item in body["agents"])
    assert all(
        item["globalSkillsPath"].startswith(expected_prefix) for item in body["agents"]
    )
    assert [item["id"] for item in body["skills"]] == list(SKILLS)
    assert [item["name"] for item in body["skills"]] == list(SKILLS.values())
    assert "path" not in body["agents"][0]


def test_capabilities_detect_existing_agent_configuration_without_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bundled_skills: Path
) -> None:
    monkeypatch.setattr(coding_agents.platform, "system", lambda: "Linux")
    monkeypatch.setattr(coding_agents.shutil, "which", lambda name: None)
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)

    body = (
        TestClient(_app(home, bundled_skills))
        .get("/web/coding-agents/capabilities")
        .json()
    )

    codex = next(agent for agent in body["agents"] if agent["id"] == "codex")
    assert codex["available"] is True
    assert codex["version"] == ""


def test_preview_lists_only_files_from_the_selected_bundled_skill(
    tmp_path: Path, bundled_skills: Path
) -> None:
    response = TestClient(_app(tmp_path / "home", bundled_skills)).get(
        "/web/coding-agents/skills/agentkit-cli/preview"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "agentkit-cli"
    assert body["name"] == "AgentKit 平台操作技能"
    assert [item["path"] for item in body["files"]] == [
        "SKILL.md",
        "references/guide.md",
    ]
    assert all(item["previewable"] for item in body["files"])
    assert "name: agentkit-cli" in body["files"][0]["content"]


def test_preview_rejects_unknown_skill_ids(
    tmp_path: Path, bundled_skills: Path
) -> None:
    response = TestClient(_app(tmp_path / "home", bundled_skills)).get(
        "/web/coding-agents/skills/../../private/preview"
    )
    unknown = TestClient(_app(tmp_path / "home", bundled_skills)).get(
        "/web/coding-agents/skills/untrusted-skill/preview"
    )

    assert response.status_code == 404
    assert unknown.status_code == 422


@pytest.mark.parametrize("system", ["Darwin", "Linux", "Windows"])
def test_configure_installs_selected_bundled_skills_globally(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    bundled_skills: Path,
    system: str,
) -> None:
    monkeypatch.setattr(coding_agents.platform, "system", lambda: system)
    monkeypatch.setattr(coding_agents.shutil, "which", lambda name: f"/tools/{name}")
    home = tmp_path / "home"
    response = TestClient(_app(home, bundled_skills)).post(
        "/web/coding-agents/install",
        json={
            "agents": ["trae", "claude-code", "codex"],
            "skills": ["agentkit-cli"],
        },
    )

    assert response.status_code == 200
    assert len(response.json()["installations"]) == 3
    for relative in (
        ".trae/skills/agentkit-cli",
        ".claude/skills/agentkit-cli",
        ".agents/skills/agentkit-cli",
    ):
        installed = home / relative
        assert (installed / "SKILL.md").is_file()
        assert (installed / "references/guide.md").read_text() == "# Guide\n"
    assert not (home / ".claude/skills/veadk-agent-development").exists()


def test_configure_atomically_updates_existing_bundled_skill(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bundled_skills: Path
) -> None:
    monkeypatch.setattr(coding_agents.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(coding_agents.shutil, "which", lambda name: f"/tools/{name}")
    home = tmp_path / "home"
    existing = home / ".claude/skills/agentkit-cli"
    existing.mkdir(parents=True)
    (existing / "SKILL.md").write_text("old", encoding="utf-8")
    (existing / "stale.md").write_text("stale", encoding="utf-8")

    response = TestClient(_app(home, bundled_skills)).post(
        "/web/coding-agents/install",
        json={"agents": ["claude-code"], "skills": ["agentkit-cli"]},
    )

    assert response.status_code == 200
    assert "name: agentkit-cli" in (existing / "SKILL.md").read_text()
    assert not (existing / "stale.md").exists()


def test_configure_rejects_unknown_or_duplicate_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bundled_skills: Path
) -> None:
    monkeypatch.setattr(coding_agents.platform, "system", lambda: "Linux")
    monkeypatch.setattr(coding_agents.shutil, "which", lambda name: f"/tools/{name}")
    client = TestClient(_app(tmp_path / "home", bundled_skills))

    unknown = client.post(
        "/web/coding-agents/install",
        json={"agents": ["trae"], "skills": ["untrusted-skill"]},
    )
    removed = client.post(
        "/web/coding-agents/install",
        json={"agents": ["codex"], "skills": ["veadk-agent-development"]},
    )
    duplicate = client.post(
        "/web/coding-agents/install",
        json={"agents": ["trae", "trae"], "skills": ["agentkit-cli"]},
    )

    assert unknown.status_code == 422
    assert removed.status_code == 422
    assert duplicate.status_code == 400


def test_configure_rejects_symlinked_global_skills_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bundled_skills: Path
) -> None:
    monkeypatch.setattr(coding_agents.platform, "system", lambda: "Linux")
    monkeypatch.setattr(coding_agents.shutil, "which", lambda name: f"/tools/{name}")
    home = tmp_path / "home"
    outside = tmp_path / "outside"
    home.mkdir()
    outside.mkdir()
    (home / ".trae").symlink_to(outside, target_is_directory=True)

    response = TestClient(_app(home, bundled_skills)).post(
        "/web/coding-agents/install",
        json={"agents": ["trae"], "skills": ["agentkit-cli"]},
    )

    assert response.status_code == 409
    assert not (outside / "skills").exists()


def test_packaged_frontend_contains_only_the_canonical_cli_skill() -> None:
    repository = Path(__file__).parents[2]
    roots = (
        repository / "frontend/public/coding-agent-skills",
        repository / "veadk/webui/coding-agent-skills",
    )

    for root in roots:
        assert sorted(path.name for path in root.iterdir() if path.is_dir()) == sorted(
            SKILLS
        )
        for skill_id in SKILLS:
            skill_md = (root / skill_id / "SKILL.md").read_text(encoding="utf-8")
            assert f"name: {skill_id}" in skill_md


def test_launch_route_is_not_exposed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bundled_skills: Path
) -> None:
    monkeypatch.setattr(coding_agents.platform, "system", lambda: "Darwin")

    response = TestClient(_app(tmp_path / "home", bundled_skills)).post(
        "/web/coding-agents/launch", json={"agent": "codex"}
    )

    assert response.status_code == 404
