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

from typing import Any

import pytest

from frontend.server.evaluation_automation.models import AutoEvaluationCase
from frontend.server.evaluation_automation.repository import (
    AgentKitAutoEvaluationRepository,
)


@pytest.mark.asyncio
async def test_agentkit_repository_creates_and_lists_an_auto_dataset() -> None:
    calls: list[dict[str, Any]] = []
    created = False

    async def post(
        *, action: str, payload: dict[str, Any], query: dict[str, str] | None = None
    ) -> dict[str, Any]:
        nonlocal created
        calls.append({"action": action, "payload": payload, "query": query})
        if action == "ListEvaluationSets" and query == {"ProjectName": "support"}:
            return {
                "Result": {
                    "EvaluationSets": [
                        {"Id": "other", "Name": "other", "WorkspaceId": "ws"}
                    ]
                }
            }
        if action == "ListEvaluationSets":
            name = payload.get("Name")
            if created and name == "客服助手_auto_good_case":
                return {
                    "Result": {
                        "EvaluationSets": [
                            {
                                "Id": "auto-good",
                                "Name": name,
                                "WorkspaceId": "ws",
                            }
                        ]
                    }
                }
            return {"Result": {"EvaluationSets": []}}
        if action == "CreateEvaluationSet":
            created = True
            return {"Result": {"EvaluationSetId": "auto-good"}}
        if action == "BatchCreateEvaluationSetItems":
            return {
                "Result": {
                    "ItemOutputs": [
                        {"ItemId": "item-1", "ItemKey": "key-1", "IsNewItem": True}
                    ]
                }
            }
        if action == "ListEvaluationSetItems":
            return {
                "Result": {
                    "Items": [
                        {
                            "ItemId": "item-1",
                            "ItemKey": "key-1",
                            "Turns": [
                                {
                                    "FieldDataList": [
                                        {
                                            "Key": "score",
                                            "Content": {"Text": "0.92"},
                                        },
                                        {
                                            "Key": "reason",
                                            "Content": {"Text": "回答完整。"},
                                        },
                                        {
                                            "Key": "source",
                                            "Content": {"Text": "auto"},
                                        },
                                    ]
                                }
                            ],
                        }
                    ]
                }
            }
        raise AssertionError(action)

    repository = AgentKitAutoEvaluationRepository(post, project_name="support")
    case = AutoEvaluationCase(
        id="",
        itemKey="key-1",
        kind="good",
        input="问题",
        output="回答",
        agentName="客服助手",
        sessionId="session",
        messageId="message",
        runtimeId="runtime",
        invocationId="invocation",
        userId="user",
        createdAt="2026-08-05T10:00:00+08:00",
        score=0.92,
        reason="回答完整。",
        evaluatorVersion="v1",
    )

    stored = await repository.upsert(case)
    items = await repository.list_cases(agent_name="客服助手")

    assert stored.id == "item-1"
    assert items[0].score == 0.92
    create_call = next(
        call for call in calls if call["action"] == "CreateEvaluationSet"
    )
    field_keys = {
        field["Key"]
        for field in create_call["payload"]["EvaluationSetSchema"]["FieldSchemas"]
    }
    assert {"source", "score", "reason", "evaluator_version"} <= field_keys
