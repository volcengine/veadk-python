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

from veadk.skills.skill import Skill
from veadk.skills.utils import _get_cloud_credentials
from veadk.tools.builtin_tools.create_agent.sources import (
    AgentKitKnowledgeSource,
    AgentKitSkillCenterSource,
    BuiltinToolResourceSource,
    CloudCredentials,
    SkillHubSearchSource,
    SkillResourceSource,
)


@pytest.mark.asyncio
async def test_skill_source_uses_space_and_skill_id_as_ref(monkeypatch) -> None:
    monkeypatch.setattr(
        "veadk.tools.builtin_tools.create_agent.sources.skills.load_skills_from_cloud",
        lambda source_id, **kwargs: [
            Skill(
                name="writer",
                description="Write reports",
                path="writer",
                id="skill-9",
                skill_space_id=source_id,
                source_type="skillhub",
                version_id="v3",
            )
        ],
    )

    result = await SkillResourceSource("sp-public").collect()

    assert result.status.status == "ok"
    assert result.resources[0].descriptor.ref == "sp-public:skill-9"
    assert result.resources[0].descriptor.version == "v3"


@pytest.mark.asyncio
async def test_skill_source_reports_collection_failure(monkeypatch) -> None:
    def fail(source_id: str, **kwargs):
        raise RuntimeError(f"cannot list {source_id}")

    monkeypatch.setattr(
        "veadk.tools.builtin_tools.create_agent.sources.skills.load_skills_from_cloud",
        fail,
    )

    result = await SkillResourceSource("sp-public").collect()

    assert result.status.status == "error"
    assert result.status.count == 0
    assert result.status.message == "cannot list sp-public"


@pytest.mark.asyncio
async def test_agentkit_skill_center_skips_without_credentials() -> None:
    source = AgentKitSkillCenterSource(credential_resolver=lambda context: None)

    result = await source.collect()

    assert result.resources == []
    assert result.status.model_dump() == {
        "source": "skill_space:agentkit",
        "status": "skipped",
        "count": 0,
        "message": "AK/SK or STS credentials are unavailable.",
        "search_keywords": [],
    }


@pytest.mark.asyncio
async def test_agentkit_skill_center_paginates_spaces_and_skills() -> None:
    space_requests = []
    skill_requests = []

    class Client:
        def list_skill_spaces(self, request):
            space_requests.append(request)
            if request.page_number == 1:
                return SimpleNamespace(
                    items=[
                        SimpleNamespace(
                            id="ss-one",
                            name="Team One",
                            project_name="project-one",
                        )
                    ],
                    total_count=2,
                )
            return SimpleNamespace(
                items=[
                    SimpleNamespace(
                        id="ss-two",
                        name="Team Two",
                        project_name="project-two",
                    )
                ],
                total_count=2,
            )

        def list_skills_by_skill_space(self, request):
            skill_requests.append(request)
            if request.skill_space_id == "ss-one" and request.page_number == 1:
                return SimpleNamespace(
                    items=[
                        SimpleNamespace(
                            skill_id="skill-a",
                            skill_name="Writer",
                            skill_description="Write a report",
                            version="v1",
                            skill_status="Published",
                        )
                    ],
                    total_count=2,
                )
            if request.skill_space_id == "ss-one":
                return SimpleNamespace(
                    items=[
                        SimpleNamespace(
                            skill_id="skill-b",
                            skill_name="Reviewer",
                            skill_description="Review a report",
                            version="v2",
                            skill_status="Published",
                        )
                    ],
                    total_count=2,
                )
            return SimpleNamespace(
                items=[
                    SimpleNamespace(
                        skill_id="skill-c",
                        skill_name="Analyst",
                        skill_description="Analyze data",
                        version="v3",
                        skill_status="Published",
                    )
                ],
                total_count=1,
            )

    source = AgentKitSkillCenterSource(
        client_factory=lambda credentials, region: Client(),
        credential_resolver=lambda context: CloudCredentials("ak", "sk", "sts"),
    )

    result = await source.collect()

    assert [request.page_number for request in space_requests] == [1, 2]
    assert sorted(
        (request.skill_space_id, request.page_number) for request in skill_requests
    ) == [("ss-one", 1), ("ss-one", 2), ("ss-two", 1)]
    assert [resource.descriptor.ref for resource in result.resources] == [
        "ss-one:skill-a",
        "ss-one:skill-b",
        "ss-two:skill-c",
    ]
    assert result.status.status == "ok"
    assert result.status.count == 3
    first = result.resources[0]
    assert first.descriptor.source == "skill_space:ss-one"
    assert first.descriptor.version == "v1"
    assert first.descriptor.metadata["space_name"] == "Team One"
    assert first.payload.skill_space_id == "ss-one"
    assert first.payload.source_type == "skillspace"
    assert first.payload.version_id == "v1"


@pytest.mark.asyncio
async def test_agentkit_skill_center_filters_discovered_spaces() -> None:
    skill_space_ids = []

    class Client:
        def list_skill_spaces(self, request):
            return SimpleNamespace(
                items=[
                    SimpleNamespace(id="ss-one", name="One", project_name="p"),
                    SimpleNamespace(id="ss-two", name="Two", project_name="p"),
                ],
                total_count=2,
            )

        def list_skills_by_skill_space(self, request):
            skill_space_ids.append(request.skill_space_id)
            return SimpleNamespace(items=[], total_count=0)

    source = AgentKitSkillCenterSource(
        ["ss-two"],
        client_factory=lambda credentials, region: Client(),
        credential_resolver=lambda context: CloudCredentials("ak", "sk"),
    )

    result = await source.collect()

    assert result.status.status == "ok"
    assert skill_space_ids == ["ss-two"]


@pytest.mark.parametrize(
    ("cloud_provider", "expected_region"),
    [("volcengine", "cn-beijing"), ("byteplus", "ap-southeast-1")],
)
def test_agentkit_skill_center_uses_provider_default_region(
    monkeypatch, cloud_provider: str, expected_region: str
) -> None:
    monkeypatch.delenv("AGENTKIT_CLOUD_PROVIDER", raising=False)
    monkeypatch.setenv("CLOUD_PROVIDER", cloud_provider)
    monkeypatch.delenv("AGENTKIT_TOOL_REGION", raising=False)
    monkeypatch.delenv("REGION", raising=False)

    assert AgentKitSkillCenterSource().region == expected_region


def test_agentkit_skill_center_prefers_agentkit_provider_and_byteplus_region(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("CLOUD_PROVIDER", "volcengine")
    monkeypatch.setenv("BYTEPLUS_REGION", "ap-southeast-2")
    monkeypatch.delenv("AGENTKIT_TOOL_REGION", raising=False)

    assert AgentKitSkillCenterSource().region == "ap-southeast-2"


def test_agentkit_skill_center_uses_cloud_safe_default_concurrency() -> None:
    assert AgentKitSkillCenterSource()._max_concurrency == 2


@pytest.mark.asyncio
async def test_skill_hub_search_source_uses_and_reports_keywords() -> None:
    calls: list[str] = []

    async def search(keyword: str) -> dict:
        calls.append(keyword)
        return {
            "Skills": [
                {
                    "Slug": "public/research-assistant",
                    "Name": "Research Assistant",
                    "Description": f"Matched {keyword}",
                    "EvaluationMetadata": {"skill_version": "v2"},
                }
            ]
        }

    result = await SkillHubSearchSource(
        ["AgentKit", "公开资料"],
        searcher=search,
    ).collect()

    assert calls == ["AgentKit", "公开资料"]
    assert result.status.model_dump() == {
        "source": "skill_hub:public",
        "status": "ok",
        "count": 1,
        "message": None,
        "search_keywords": ["AgentKit", "公开资料"],
    }
    resource = result.resources[0]
    assert resource.descriptor.ref == "skill_hub:public/research-assistant"
    assert resource.descriptor.version == "v2"
    assert resource.payload.source_type == "findskill"
    assert resource.payload.slug == "public/research-assistant"


@pytest.mark.asyncio
async def test_agentkit_knowledge_source_paginates_without_keyword_filter() -> None:
    requests = []
    responses = [
        SimpleNamespace(
            knowledge_bases=[
                SimpleNamespace(
                    knowledge_id="kb-agentkit-1",
                    provider_knowledge_id="provider_index",
                    provider_type="VIKINGDB_KNOWLEDGE",
                    name="handbook",
                    description="Internal handbook",
                    project_name="default",
                    region="cn-beijing",
                )
            ],
            next_token="next",
        ),
        SimpleNamespace(knowledge_bases=[], next_token=""),
    ]

    class Client:
        def list_knowledge_bases(self, request):
            requests.append(request)
            return responses.pop(0)

    source = AgentKitKnowledgeSource(
        client_factory=lambda credentials, region: Client(),
        credential_resolver=lambda context: CloudCredentials("ak", "sk", "sts"),
    )

    result = await source.collect()

    assert len(requests) == 2
    assert requests[0].next_token is None
    assert requests[1].next_token == "next"
    assert result.resources[0].descriptor.ref == "agentkit_kb:kb-agentkit-1"
    assert result.resources[0].descriptor.name == "handbook"


def test_skill_sources_use_byteplus_credentials(monkeypatch) -> None:
    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "byteplus-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "byteplus-sk")
    monkeypatch.setenv("BYTEPLUS_SESSION_TOKEN", "byteplus-sts")
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "volcengine-ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "volcengine-sk")

    assert _get_cloud_credentials() == (
        "byteplus-ak",
        "byteplus-sk",
        "byteplus-sts",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("cloud_provider", ["volcengine", "byteplus"])
async def test_builtin_tool_source_is_provider_independent(
    monkeypatch, cloud_provider: str
) -> None:
    monkeypatch.setenv("CLOUD_PROVIDER", cloud_provider)
    monkeypatch.setattr(
        "veadk.tools.builtin_tools.create_agent.sources.builtin_tools.list_builtin_tools",
        lambda: ["web_search", "run_code"],
    )

    result = await BuiltinToolResourceSource().collect()

    assert result.status.model_dump() == {
        "source": "veadk_builtin_tools",
        "status": "ok",
        "count": 2,
        "message": None,
        "search_keywords": [],
    }
    assert [item.descriptor.ref for item in result.resources] == [
        "veadk_tool:web_search",
        "veadk_tool:run_code",
    ]
    assert [item.payload for item in result.resources] == ["web_search", "run_code"]
    assert all(item.descriptor.kind == "tool" for item in result.resources)
