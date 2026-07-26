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

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.adk.agents import LlmAgent
from google.adk.sessions import InMemorySessionService

import veadk.integrations.agentkit.app as agentkit_app
from veadk.integrations.agentkit import session_capabilities as capabilities


async def _service() -> tuple[
    capabilities.SessionCapabilityService,
    InMemorySessionService,
    LlmAgent,
]:
    root_agent = LlmAgent(name="agent", model="gemini-2.0-flash")
    session_service = InMemorySessionService()
    service = capabilities.SessionCapabilityService(
        root_agent=root_agent,
        session_service=session_service,
    )
    return service, session_service, root_agent


@pytest.mark.asyncio
async def test_tool_overlay_persists_in_session_state_and_is_isolated() -> None:
    service, session_service, _ = await _service()
    await session_service.create_session(
        app_name="agent", user_id="user-1", session_id="session-a"
    )
    await session_service.create_session(
        app_name="agent", user_id="user-1", session_id="session-b"
    )

    updated = await service.add_capability(
        app_name="agent",
        user_id="user-1",
        session_id="session-a",
        request=capabilities.AddCapabilityRequest(
            kind="tool",
            name="get_city_weather",
            expected_revision=0,
        ),
    )

    assert updated.revision == 1
    assert [item.name for item in updated.tools if item.custom] == ["get_city_weather"]
    stored = await session_service.get_session(
        app_name="agent", user_id="user-1", session_id="session-a"
    )
    assert stored is not None
    assert stored.state[capabilities.SESSION_CAPABILITIES_STATE_KEY] == {
        "schema_version": 1,
        "revision": 1,
        "tools": [{"ref": "builtin:get_city_weather"}],
        "skills": [],
    }
    isolated = await service.get_capabilities(
        app_name="agent", user_id="user-1", session_id="session-b"
    )
    assert isolated.revision == 0
    assert not any(item.custom for item in isolated.tools)


@pytest.mark.asyncio
async def test_base_capability_cannot_be_added_or_removed() -> None:
    def base_tool(city: str) -> str:
        return city

    root_agent = LlmAgent(
        name="agent",
        model="gemini-2.0-flash",
        tools=[base_tool],
    )
    session_service = InMemorySessionService()
    service = capabilities.SessionCapabilityService(
        root_agent=root_agent,
        session_service=session_service,
    )
    await session_service.create_session(
        app_name="agent", user_id="user-1", session_id="session-a"
    )

    response = await service.get_capabilities(
        app_name="agent", user_id="user-1", session_id="session-a"
    )
    assert [(item.name, item.custom) for item in response.tools] == [
        ("base_tool", False)
    ]
    with pytest.raises(capabilities.CapabilityConflictError):
        await service.remove_capability(
            app_name="agent",
            user_id="user-1",
            session_id="session-a",
            capability_id="base:tool:base_tool",
        )


@pytest.mark.asyncio
async def test_remove_custom_capability_and_reject_stale_revision() -> None:
    service, session_service, _ = await _service()
    await session_service.create_session(
        app_name="agent", user_id="user-1", session_id="session-a"
    )
    added = await service.add_capability(
        app_name="agent",
        user_id="user-1",
        session_id="session-a",
        request=capabilities.AddCapabilityRequest(kind="tool", name="get_city_weather"),
    )

    with pytest.raises(capabilities.CapabilityConflictError):
        await service.remove_capability(
            app_name="agent",
            user_id="user-1",
            session_id="session-a",
            capability_id="session:tool:get_city_weather",
            expected_revision=0,
        )

    removed = await service.remove_capability(
        app_name="agent",
        user_id="user-1",
        session_id="session-a",
        capability_id="session:tool:get_city_weather",
        expected_revision=added.revision,
    )
    assert removed.revision == 2
    assert not any(item.custom for item in removed.tools)


@pytest.mark.asyncio
async def test_build_agent_mounts_tool_without_mutating_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, session_service, root_agent = await _service()
    await session_service.create_session(
        app_name="agent", user_id="user-1", session_id="session-a"
    )
    await service.add_capability(
        app_name="agent",
        user_id="user-1",
        session_id="session-a",
        request=capabilities.AddCapabilityRequest(kind="tool", name="get_city_weather"),
    )

    def mounted_tool(city: str) -> str:
        return city

    monkeypatch.setattr(capabilities, "get_builtin_tool", lambda name: mounted_tool)

    run_agent = await service.build_agent(
        app_name="agent", user_id="user-1", session_id="session-a"
    )

    assert [capabilities._tool_name(tool) for tool in run_agent.tools] == [
        "mounted_tool"
    ]
    assert root_agent.tools == []


@pytest.mark.asyncio
async def test_skill_reference_is_persisted_as_metadata_only() -> None:
    service, session_service, _ = await _service()
    await session_service.create_session(
        app_name="agent", user_id="user-1", session_id="session-a"
    )

    response = await service.add_capability(
        app_name="agent",
        user_id="user-1",
        session_id="session-a",
        request=capabilities.AddCapabilityRequest(
            kind="skill",
            name="pdf-reader",
            skill_source_id="skill-space-1",
            description="Read PDF files.",
            version="1.2.0",
        ),
    )

    custom_skill = response.skills[0]
    assert custom_skill.custom is True
    assert custom_skill.name == "pdf-reader"
    stored = await session_service.get_session(
        app_name="agent", user_id="user-1", session_id="session-a"
    )
    assert stored is not None
    raw_skill = stored.state[capabilities.SESSION_CAPABILITIES_STATE_KEY]["skills"][0]
    assert raw_skill == {
        "id": custom_skill.id,
        "skill_source_id": "skill-space-1",
        "name": "pdf-reader",
        "description": "Read PDF files.",
        "version": "1.2.0",
    }


@pytest.mark.asyncio
async def test_build_agent_loads_skill_without_mutating_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, session_service, root_agent = await _service()
    await session_service.create_session(
        app_name="agent", user_id="user-1", session_id="session-a"
    )
    await service.add_capability(
        app_name="agent",
        user_id="user-1",
        session_id="session-a",
        request=capabilities.AddCapabilityRequest(
            kind="skill",
            name="pdf-reader",
            skill_source_id="skill-space-1",
        ),
    )
    loaded = []

    async def load_skill(skill_source_id: str, name: str, version: str) -> object:
        loaded.append((skill_source_id, name, version))
        return SimpleNamespace(name=name, description="Read PDF files.")

    monkeypatch.setattr(capabilities, "_load_remote_skill", load_skill)

    run_agent = await service.build_agent(
        app_name="agent", user_id="user-1", session_id="session-a"
    )

    assert loaded == [("skill-space-1", "pdf-reader", "")]
    assert len(run_agent.tools) == 1
    assert type(run_agent.tools[0]).__name__ == "SkillToolset"
    assert "`pdf-reader`" in run_agent.instruction
    assert "call list_skills" in run_agent.instruction
    assert root_agent.tools == []
    assert root_agent.instruction == ""


@pytest.mark.asyncio
async def test_findskill_reference_uses_slug_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = []

    def load_findskill(slug: str, name: str, version: str) -> object:
        loaded.append((slug, name, version))
        return SimpleNamespace(name=name, description="Public skill.")

    monkeypatch.setattr(capabilities, "_load_findskill_skill", load_findskill)

    skill = await capabilities._load_remote_skill(
        "findskill:volcengine/example/public-skill",
        "public-skill",
        "1.2.3",
    )

    assert skill.name == "public-skill"
    assert loaded == [("volcengine/example/public-skill", "public-skill", "1.2.3")]


@pytest.mark.asyncio
async def test_harness_routes_are_prioritized_before_agentkit_root_mount() -> None:
    service, session_service, _ = await _service()
    await session_service.create_session(
        app_name="agent", user_id="user-1", session_id="session-a"
    )
    app = FastAPI()
    app.mount("/", FastAPI())
    capabilities.mount_session_capability_routes(app=app, service=service)
    agentkit_app._prioritize_platform_routes(app)

    response = TestClient(app).get(
        "/harness/apps/agent/users/user-1/sessions/session-a/capabilities"
    )
    harness_route_index = next(
        index
        for index, route in enumerate(app.router.routes)
        if getattr(route, "path", "").startswith("/harness/")
        or any(
            getattr(included_route, "path", "").startswith("/harness/")
            for included_route in getattr(
                getattr(route, "original_router", None), "routes", ()
            )
        )
    )
    root_mount_index = next(
        index
        for index, route in enumerate(app.router.routes)
        if getattr(route, "path", None) == ""
    )

    assert response.status_code == 200
    assert response.json()["revision"] == 0
    assert harness_route_index < root_mount_index


@pytest.mark.asyncio
async def test_harness_skill_catalog_routes_list_spaces_and_skills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, _ = await _service()

    class FakeSkillClient:
        def __init__(self, region: str) -> None:
            self.region = region

        def list_skill_spaces(self, request: object) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                items=[
                    SimpleNamespace(
                        id=f"space-{self.region}",
                        name=f"{self.region} Skills",
                        description="Shared skills",
                        status="active",
                        project_name="default",
                        update_time_stamp="",
                        relations=[object()],
                    )
                ]
            )

        def list_skills_by_skill_space(self, request: object) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                items=[
                    SimpleNamespace(
                        skill_id="skill-1",
                        skill_name="writer",
                        skill_description="Write content",
                        version="1.0.0",
                        skill_status="active",
                    )
                ],
                total_count=1,
            )

    monkeypatch.setattr(
        capabilities,
        "_skill_catalog_client",
        lambda region: FakeSkillClient(region),
    )
    app = FastAPI()
    capabilities.mount_session_capability_routes(app=app, service=service)
    client = TestClient(app)

    spaces = client.get("/harness/skills/spaces?region=all")
    skills = client.get(
        "/harness/skills/spaces/space-cn-beijing/skills?region=cn-beijing"
    )

    assert spaces.status_code == 200
    assert [item["region"] for item in spaces.json()["items"]] == [
        "cn-beijing",
        "cn-shanghai",
    ]
    assert skills.status_code == 200
    assert skills.json()["items"][0] == {
        "skillId": "skill-1",
        "skillName": "writer",
        "skillDescription": "Write content",
        "version": "1.0.0",
        "skillStatus": "active",
    }


@pytest.mark.asyncio
async def test_harness_findskill_route_returns_public_slugs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, _ = await _service()

    async def search_findskill(**kwargs: object) -> dict[str, object]:
        assert kwargs == {"query": "pdf", "page_number": 1, "page_size": 20}
        return {
            "items": [
                {
                    "slug": "volcengine/las/pdf-reader",
                    "name": "pdf-reader",
                    "description": "Read PDF files",
                    "sourceType": "volcengine",
                    "sourceRepo": "volcengine/las",
                    "downloadCount": 42,
                    "evaluationScore": 4.8,
                    "version": "1.0.0",
                    "updatedAt": "2026-07-26T00:00:00+08:00",
                }
            ],
            "totalCount": 1,
        }

    monkeypatch.setattr(capabilities, "_search_findskill", search_findskill)
    app = FastAPI()
    capabilities.mount_session_capability_routes(app=app, service=service)

    response = TestClient(app).get("/harness/skills/findskill?query=pdf")

    assert response.status_code == 200
    assert response.json()["items"][0]["slug"] == "volcengine/las/pdf-reader"
