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
)


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
            if list_count == 3:
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
        "CreateEvaluationSet",
        "ListEvaluationSets",
    ]
    assert calls[0]["query"] == {"ProjectName": "support"}
    assert calls[1]["query"] == {
        "ProjectName": "support",
        "WorkspaceId": "workspace-1",
    }
    assert calls[2]["query"] == {
        "ProjectName": "support",
        "WorkspaceId": "workspace-1",
    }
    create_payload = calls[2]["payload"]
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
            if find_count < 4:
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
        "CreateEvaluationSet",
        "ListEvaluationSets",
        "ListEvaluationSets",
    ]


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
