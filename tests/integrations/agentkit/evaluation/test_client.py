# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from typing import Any

import pytest

from veadk.integrations.agentkit.evaluation.client import (
    AgentKitEvaluationDatasetsClient,
    AgentKitOpenApiError,
    feedback_set_name,
)


def test_feedback_set_name_preserves_suffix_within_agentkit_limit() -> None:
    name = feedback_set_name("a" * 100, "good")

    assert len(name) == 50
    assert name.endswith("_good_case")


class _HiddenDuplicateBackend:
    def __init__(self, *, race_fallback: bool = False) -> None:
        self.race_fallback = race_fallback
        self.created_names: list[str] = []
        self.visible_sets = [
            {
                "Id": "other-set",
                "Name": "其他评测集",
                "WorkspaceId": "workspace-1",
            }
        ]

    async def __call__(
        self,
        *,
        action: str,
        payload: dict[str, Any],
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        del query
        if action == "ListEvaluationSets":
            requested_name = str(payload.get("Name") or "")
            items = self.visible_sets
            if requested_name:
                items = [item for item in items if item["Name"] == requested_name]
            return {"Result": {"EvaluationSets": items}}
        if action != "CreateEvaluationSet":
            raise AssertionError(action)

        name = str(payload["Name"])
        self.created_names.append(name)
        if name == "dt_good_case":
            raise AgentKitOpenApiError(
                "601104504",
                "dataset name is duplicated in this space",
            )
        self.visible_sets.append(
            {
                "Id": "fallback-set",
                "Name": name,
                "WorkspaceId": "workspace-1",
            }
        )
        if self.race_fallback:
            raise AgentKitOpenApiError(
                "601104504",
                "dataset name is duplicated in this space",
            )
        return {"Result": {"EvaluationSetId": "fallback-set"}}


async def _no_sleep(delay: float) -> None:
    del delay


@pytest.mark.asyncio
async def test_ensure_set_creates_and_resolves_workspace() -> None:
    calls: list[dict[str, Any]] = []
    list_count = 0

    async def post(
        *,
        action: str,
        payload: dict[str, Any],
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        nonlocal list_count
        calls.append({"action": action, "payload": payload, "query": query})
        if action == "ListEvaluationSets":
            list_count += 1
            if list_count == 1:
                return {
                    "Result": {
                        "EvaluationSets": [
                            {
                                "Id": "existing-set",
                                "Name": "其他评测集",
                                "WorkspaceId": "workspace-1",
                            }
                        ]
                    }
                }
            if list_count == 4:
                return {
                    "Result": {
                        "EvaluationSets": [
                            {
                                "Id": "set-1",
                                "Name": "客服助手_good_case",
                                "WorkspaceId": "workspace-1",
                            }
                        ]
                    }
                }
            return {"Result": {"EvaluationSets": []}}
        if action == "CreateEvaluationSet":
            return {"Result": {"EvaluationSetId": "set-1"}}
        raise AssertionError(action)

    client = AgentKitEvaluationDatasetsClient(post, project_name="support")
    evaluation_set = await client.ensure_feedback_set("客服助手", "good")

    assert evaluation_set.id == "set-1"
    assert evaluation_set.workspace_id == "workspace-1"
    assert [call["action"] for call in calls] == [
        "ListEvaluationSets",
        "ListEvaluationSets",
        "ListEvaluationSets",
        "CreateEvaluationSet",
        "ListEvaluationSets",
    ]
    assert calls[0]["query"] == {"ProjectName": "support"}
    assert calls[1]["query"] == {
        "ProjectName": "support",
        "WorkspaceId": "workspace-1",
    }
    assert calls[3]["query"] == {
        "ProjectName": "support",
        "WorkspaceId": "workspace-1",
    }
    create_payload = calls[3]["payload"]
    assert create_payload["Name"] == "客服助手_good_case"
    assert "BizCategory" not in create_payload
    field_keys = {
        field["Key"] for field in create_payload["EvaluationSetSchema"]["FieldSchemas"]
    }
    assert {"input", "output", "session_id", "message_id"} <= field_keys


@pytest.mark.asyncio
async def test_ensure_set_fails_when_created_set_never_becomes_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def post(
        *,
        action: str,
        payload: dict[str, Any],
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        del payload, query
        if action == "ListEvaluationSets":
            return {
                "Result": {
                    "EvaluationSets": [
                        {
                            "Id": "other-set",
                            "Name": "其他评测集",
                            "WorkspaceId": "workspace-1",
                        }
                    ]
                }
            }
        if action == "CreateEvaluationSet":
            return {"Result": {"EvaluationSetId": "set-1"}}
        raise AssertionError(action)

    async def fake_sleep(delay: float) -> None:
        del delay

    monkeypatch.setattr(
        "veadk.integrations.agentkit.evaluation.client.asyncio.sleep",
        fake_sleep,
    )

    client = AgentKitEvaluationDatasetsClient(post, project_name="default")

    with pytest.raises(
        RuntimeError,
        match="created evaluation set is not visible",
    ):
        await client.ensure_feedback_set("客服助手", "good")


@pytest.mark.asyncio
async def test_ensure_set_recovers_when_duplicate_becomes_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    sleeps: list[float] = []
    find_count = 0

    async def post(
        *,
        action: str,
        payload: dict[str, Any],
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        del payload, query
        nonlocal find_count
        calls.append(action)
        if action == "ListEvaluationSets":
            find_count += 1
            if find_count == 1:
                return {
                    "Result": {
                        "EvaluationSets": [
                            {
                                "Id": "other-set",
                                "Name": "其他评测集",
                                "WorkspaceId": "workspace-1",
                            }
                        ]
                    }
                }
            if find_count < 5:
                return {"Result": {"EvaluationSets": []}}
            return {
                "Result": {
                    "EvaluationSets": [
                        {
                            "Id": "existing-set",
                            "Name": "客服助手_good_case",
                            "WorkspaceId": "workspace-1",
                        }
                    ]
                }
            }
        if action == "CreateEvaluationSet":
            raise AgentKitOpenApiError(
                "601104504",
                "dataset name is duplicated in this space",
            )
        raise AssertionError(action)

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(
        "veadk.integrations.agentkit.evaluation.client.asyncio.sleep",
        fake_sleep,
    )

    client = AgentKitEvaluationDatasetsClient(post, project_name="default")
    evaluation_set = await client.ensure_feedback_set("客服助手", "good")

    assert evaluation_set.id == "existing-set"
    assert evaluation_set.workspace_id == "workspace-1"
    assert sleeps == [0.25, 0.5]
    assert calls == [
        "ListEvaluationSets",
        "ListEvaluationSets",
        "ListEvaluationSets",
        "CreateEvaluationSet",
        "ListEvaluationSets",
        "ListEvaluationSets",
    ]


@pytest.mark.asyncio
async def test_ensure_set_uses_and_reuses_fallback_for_hidden_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _HiddenDuplicateBackend()
    monkeypatch.setattr(
        "veadk.integrations.agentkit.evaluation.client.asyncio.sleep",
        _no_sleep,
    )

    first_client = AgentKitEvaluationDatasetsClient(backend, project_name="default")
    first = await first_client.ensure_feedback_set("dt", "good")
    second_client = AgentKitEvaluationDatasetsClient(backend, project_name="default")
    second = await second_client.ensure_feedback_set("dt", "good")

    assert backend.created_names[0] == "dt_good_case"
    assert len(backend.created_names) == 2
    fallback_name = backend.created_names[1]
    assert fallback_name.startswith("dt_good_case_")
    assert len(fallback_name) <= 50
    assert first.id == "fallback-set"
    assert first.name == fallback_name
    assert second == first


@pytest.mark.asyncio
async def test_ensure_set_recovers_when_fallback_creation_races(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _HiddenDuplicateBackend(race_fallback=True)
    monkeypatch.setattr(
        "veadk.integrations.agentkit.evaluation.client.asyncio.sleep",
        _no_sleep,
    )

    client = AgentKitEvaluationDatasetsClient(backend, project_name="default")
    evaluation_set = await client.ensure_feedback_set("dt", "good")

    fallback_name = backend.created_names[1]
    assert fallback_name.startswith("dt_good_case_")
    assert evaluation_set.id == "fallback-set"
    assert evaluation_set.name == fallback_name


@pytest.mark.asyncio
async def test_ensure_set_propagates_non_duplicate_create_error() -> None:
    create_calls = 0

    async def post(
        *,
        action: str,
        payload: dict[str, Any],
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        del payload, query
        nonlocal create_calls
        if action == "ListEvaluationSets":
            return {
                "Result": {
                    "EvaluationSets": [
                        {
                            "Id": "other-set",
                            "Name": "其他评测集",
                            "WorkspaceId": "workspace-1",
                        }
                    ]
                }
            }
        if action == "CreateEvaluationSet":
            create_calls += 1
            raise AgentKitOpenApiError("500", "upstream unavailable")
        raise AssertionError(action)

    client = AgentKitEvaluationDatasetsClient(post, project_name="default")

    with pytest.raises(AgentKitOpenApiError, match="500: upstream unavailable"):
        await client.ensure_feedback_set("dt", "good")

    assert create_calls == 1


@pytest.mark.asyncio
async def test_upsert_item_uses_item_key_and_set_scope() -> None:
    calls: list[dict[str, Any]] = []

    async def post(
        *,
        action: str,
        payload: dict[str, Any],
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        calls.append({"action": action, "payload": payload, "query": query})
        return {
            "Result": {
                "ItemOutputs": [
                    {"ItemId": "item-1", "ItemKey": "stable-key", "IsNewItem": True}
                ]
            }
        }

    client = AgentKitEvaluationDatasetsClient(post, project_name="default")
    item = await client.upsert_item(
        evaluation_set_id="set-1",
        workspace_id="workspace-1",
        item_key="stable-key",
        fields={"input": "问题", "output": "回答"},
    )

    assert item.id == "item-1"
    assert calls[0]["action"] == "BatchCreateEvaluationSetItems"
    assert calls[0]["query"] == {
        "ProjectName": "default",
        "WorkspaceId": "workspace-1",
        "EvaluationSetId": "set-1",
    }
    assert calls[0]["payload"]["Items"][0]["ItemKey"] == "stable-key"


@pytest.mark.asyncio
async def test_list_feedback_items_reads_set_items() -> None:
    calls: list[dict[str, Any]] = []

    async def post(
        *,
        action: str,
        payload: dict[str, Any],
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        calls.append({"action": action, "payload": payload, "query": query})
        if action == "ListEvaluationSets":
            if payload.get("Name"):
                return {
                    "Result": {
                        "EvaluationSets": [
                            {
                                "Id": "set-1",
                                "Name": "客服助手_good_case",
                                "WorkspaceId": "workspace-1",
                            }
                        ]
                    }
                }
            return {
                "Result": {
                    "EvaluationSets": [
                        {
                            "Id": "workspace-probe",
                            "Name": "其他评测集",
                            "WorkspaceId": "workspace-1",
                        }
                    ]
                }
            }
        if action == "ListEvaluationSetItems":
            return {
                "Result": {
                    "Items": [
                        {
                            "ItemId": "item-1",
                            "ItemKey": "stable-key",
                            "Turns": [
                                {
                                    "FieldDataList": [
                                        {
                                            "Key": "input",
                                            "Content": {
                                                "ContentType": "Text",
                                                "Text": "问题",
                                            },
                                        },
                                        {
                                            "Key": "output",
                                            "Content": {
                                                "ContentType": "Text",
                                                "Text": "回答",
                                            },
                                        },
                                    ]
                                }
                            ],
                        }
                    ]
                }
            }
        raise AssertionError(action)

    client = AgentKitEvaluationDatasetsClient(post, project_name="support")
    evaluation_set, items = await client.list_feedback_items(
        agent_name="客服助手",
        rating="good",
        page_size=20,
    )

    assert evaluation_set is not None
    assert evaluation_set.id == "set-1"
    assert items[0].id == "item-1"
    assert items[0].fields["input"] == "问题"
    assert items[0].fields["output"] == "回答"
    assert [call["action"] for call in calls] == [
        "ListEvaluationSets",
        "ListEvaluationSets",
        "ListEvaluationSetItems",
    ]
    assert calls[-1]["query"] == {
        "ProjectName": "support",
        "WorkspaceId": "workspace-1",
        "EvaluationSetId": "set-1",
    }
